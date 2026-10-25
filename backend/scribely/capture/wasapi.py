"""Windows system-audio capture via WASAPI loopback (PyAudioWPatch)."""

from __future__ import annotations

import asyncio
from typing import Any

from scribely.capture.base import AudioCapture, CaptureError
from scribely.capture.dsp import int16_to_float32

FRAMES_PER_BUFFER = 1024


class WasapiLoopbackCapture(AudioCapture):
    """Records what the default output device is playing ("what you hear")."""

    name = "wasapi"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pa: Any = None
        self._stream: Any = None

    async def _open(self) -> None:
        await asyncio.to_thread(self._open_blocking)

    async def _close(self) -> None:
        await asyncio.to_thread(self._close_blocking)

    def _open_blocking(self) -> None:
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            raise CaptureError(
                "WASAPI capture needs the PyAudioWPatch package, which is only available "
                "on Windows."
            ) from None

        pa = pyaudio.PyAudio()
        try:
            try:
                device = pa.get_default_wasapi_loopback()
            except OSError:
                raise CaptureError(
                    "Windows audio (WASAPI) is not available on this system."
                ) from None
            except LookupError:
                raise CaptureError(
                    "Couldn't find a loopback device for your default speakers. Check that an "
                    "output device is enabled in Windows Settings → System → Sound."
                ) from None

            channels = int(device["maxInputChannels"])
            rate = int(device["defaultSampleRate"])

            def callback(
                in_data: bytes | None, frame_count: int, time_info: Any, status: int
            ) -> tuple[None, int]:
                try:
                    if in_data:
                        self._push(int16_to_float32(in_data, channels), rate)
                except Exception as err:  # never let an exception escape into PortAudio
                    self._fail(err)
                return (None, pyaudio.paContinue)

            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=rate,
                    frames_per_buffer=FRAMES_PER_BUFFER,
                    input=True,
                    input_device_index=int(device["index"]),
                    stream_callback=callback,
                )
            except OSError as err:
                raise CaptureError(
                    f'Couldn\'t open the loopback device "{device["name"]}": {err}'
                ) from None
        except BaseException:
            pa.terminate()
            raise

        self._pa, self._stream = pa, stream
        self._log.info("capture.device", device=device["name"], rate=rate, channels=channels)

    def _close_blocking(self) -> None:
        stream, pa = self._stream, self._pa
        self._stream = self._pa = None
        try:
            if stream is not None:
                stream.stop_stream()  # blocks until the callback has returned
                stream.close()
        finally:
            if pa is not None:
                pa.terminate()
