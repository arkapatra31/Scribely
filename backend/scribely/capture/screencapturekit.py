"""macOS system-audio capture via ScreenCaptureKit (PyObjC).

ScreenCaptureKit needs the *Screen & System Audio Recording* permission even for audio-only
capture. In development the permission belongs to the terminal app running the backend.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any

from scribely.capture.base import AudioCapture, CaptureError, CapturePermissionError
from scribely.capture.dsp import planar_float32_to_frames

SAMPLE_RATE = 48_000
CHANNELS = 2
COMPLETION_TIMEOUT_SECONDS = 15.0
SC_STREAM_ERROR_USER_DECLINED = -3801

PERMISSION_MESSAGE = (
    "Scribely needs the Screen & System Audio Recording permission to hear your lecture audio. "
    "Open System Settings → Privacy & Security → Screen & System Audio Recording, turn on "
    "Scribely (or your terminal app when running from source), then restart Scribely."
)


class ScreenCaptureKitCapture(AudioCapture):
    """Records all system audio except Scribely's own output."""

    name = "screencapturekit"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._stream: Any = None
        self._output: Any = None
        self._delegate: Any = None
        self._queue: Any = None

    async def _open(self) -> None:
        fw = _frameworks()
        quartz, sck = fw["Quartz"], fw["ScreenCaptureKit"]

        quartz.CGMainDisplayID()  # initialise the CoreGraphics connection for a non-app process
        if not quartz.CGPreflightScreenCaptureAccess():
            quartz.CGRequestScreenCaptureAccess()  # shows the system prompt (first time only)
            raise CapturePermissionError(PERMISSION_MESSAGE)

        content, error = await self._await_completion(
            sck.SCShareableContent.getShareableContentWithCompletionHandler_
        )
        if error is not None:
            raise _translate_error(error, "Couldn't list displays to capture from")
        displays = content.displays()
        if not displays:
            raise CaptureError("No display found; ScreenCaptureKit needs one to capture audio.")

        content_filter = sck.SCContentFilter.alloc().initWithDisplay_excludingWindows_(
            displays[0], []
        )
        config = sck.SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setExcludesCurrentProcessAudio_(True)
        config.setSampleRate_(SAMPLE_RATE)
        config.setChannelCount_(CHANNELS)
        # Video can't be disabled; make it as cheap as possible.
        config.setWidth_(2)
        config.setHeight_(2)
        config.setMinimumFrameInterval_(fw["CoreMedia"].CMTimeMake(1, 1))

        classes = _objc_classes()
        self._output = classes.output.alloc().initWithHandler_(self._on_sample_buffer)
        self._delegate = classes.delegate.alloc().initWithHandler_(self._on_stopped)
        stream = sck.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, config, self._delegate
        )
        self._queue = fw["dispatch"].dispatch_queue_create(b"com.scribely.audio-capture", None)
        ok, error = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._output, sck.SCStreamOutputTypeAudio, self._queue, None
        )
        if not ok:
            raise _translate_error(error, "Couldn't attach the audio output")

        (error,) = await self._await_completion(stream.startCaptureWithCompletionHandler_)
        if error is not None:
            raise _translate_error(error, "Couldn't start system audio capture")
        self._stream = stream

    async def _close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            (error,) = await self._await_completion(stream.stopCaptureWithCompletionHandler_)
            if error is not None:
                self._log.warning("capture.stop_error", error=str(error.localizedDescription()))
        self._output = self._delegate = self._queue = None

    # --- ScreenCaptureKit callbacks (dispatch queue thread) --------------------------------

    def _on_sample_buffer(self, sample_buffer: Any, output_type: int) -> None:
        fw = _frameworks()
        if output_type != fw["ScreenCaptureKit"].SCStreamOutputTypeAudio:
            return
        try:
            frames = _sample_buffer_to_frames(fw["CoreMedia"], sample_buffer)
            if frames is not None:
                self._push(frames, SAMPLE_RATE)
        except Exception as err:
            self._fail(err)

    def _on_stopped(self, error: Any) -> None:
        self._fail(_translate_error(error, "System audio capture stopped unexpectedly"))

    # --- helpers ----------------------------------------------------------------------------

    async def _await_completion(self, start: Callable[[Any], None]) -> tuple[Any, ...]:
        """Call an ObjC method taking a completion handler and await the handler's arguments."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[Any, ...]] = loop.create_future()

        def resolve(args: tuple[Any, ...]) -> None:
            if not future.done():
                future.set_result(args)

        def handler(*args: Any) -> None:
            loop.call_soon_threadsafe(resolve, args)

        start(handler)
        try:
            return await asyncio.wait_for(future, COMPLETION_TIMEOUT_SECONDS)
        except TimeoutError:
            raise CaptureError("macOS did not respond to the audio capture request.") from None


def _sample_buffer_to_frames(cm: Any, sample_buffer: Any) -> Any:
    """CMSampleBuffer (ScreenCaptureKit audio: float32, non-interleaved) -> (frames, channels)."""
    if not cm.CMSampleBufferIsValid(sample_buffer):
        return None
    n_frames = int(cm.CMSampleBufferGetNumSamples(sample_buffer))
    block = cm.CMSampleBufferGetDataBuffer(sample_buffer)
    if n_frames == 0 or block is None:
        return None
    length = int(cm.CMBlockBufferGetDataLength(block))
    status, data = cm.CMBlockBufferCopyDataBytes(block, 0, length, None)
    if status != 0:
        raise CaptureError(f"Couldn't read a system audio buffer (OSStatus {status}).")
    channels = length // (n_frames * 4)
    if channels < 1:
        raise CaptureError("Received a system audio buffer in an unexpected format.")
    return planar_float32_to_frames(bytes(data), channels, n_frames)


def _translate_error(error: Any, context: str) -> CaptureError:
    if error is not None and int(error.code()) == SC_STREAM_ERROR_USER_DECLINED:
        return CapturePermissionError(PERMISSION_MESSAGE)
    detail = str(error.localizedDescription()) if error is not None else "unknown error"
    return CaptureError(f"{context}: {detail}")


@functools.cache
def _frameworks() -> dict[str, Any]:
    try:
        import CoreMedia
        import dispatch
        import Quartz
        import ScreenCaptureKit
    except ImportError:
        raise CaptureError(
            "ScreenCaptureKit capture needs macOS 13 or later with the PyObjC frameworks "
            "installed (run `uv sync` on macOS)."
        ) from None
    return {
        "CoreMedia": CoreMedia,
        "dispatch": dispatch,
        "Quartz": Quartz,
        "ScreenCaptureKit": ScreenCaptureKit,
    }


class _Classes:
    def __init__(self, output: Any, delegate: Any) -> None:
        self.output = output
        self.delegate = delegate


@functools.cache
def _objc_classes() -> _Classes:
    """Define the ObjC callback classes once per process (ObjC class names are global)."""
    import objc
    from Foundation import NSObject

    class ScribelyAudioOutput(NSObject, protocols=[objc.protocolNamed("SCStreamOutput")]):  # type: ignore[misc, call-arg]
        def initWithHandler_(self, handler: Callable[[Any, int], None]) -> Any:
            self = objc.super(ScribelyAudioOutput, self).init()
            if self is not None:
                self._handler = handler
            return self

        def stream_didOutputSampleBuffer_ofType_(
            self, stream: Any, sample_buffer: Any, output_type: int
        ) -> None:
            self._handler(sample_buffer, output_type)

    class ScribelyStreamDelegate(NSObject, protocols=[objc.protocolNamed("SCStreamDelegate")]):  # type: ignore[misc, call-arg]
        def initWithHandler_(self, handler: Callable[[Any], None]) -> Any:
            self = objc.super(ScribelyStreamDelegate, self).init()
            if self is not None:
                self._handler = handler
            return self

        def stream_didStopWithError_(self, stream: Any, error: Any) -> None:
            self._handler(error)

    return _Classes(ScribelyAudioOutput, ScribelyStreamDelegate)
