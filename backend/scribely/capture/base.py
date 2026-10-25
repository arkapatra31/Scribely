"""Backend-independent capture plumbing.

Backends receive audio on a native thread and call ``_push()``. This class converts it to
16 kHz mono float32 and hands it to the asyncio consumer of ``stream()``.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import ClassVar

import structlog

from scribely.capture.dsp import TARGET_SAMPLE_RATE, Float32Array, Resampler, to_mono

# Loopback sources deliver nothing while the system is silent. A wall-clock jump larger than
# this re-anchors chunk offsets so timestamps keep matching the video.
GAP_THRESHOLD_SECONDS = 0.5


class CaptureError(Exception):
    """Capture problem with a plain-language message safe to show the user."""


class CapturePermissionError(CaptureError):
    """The OS has not granted permission to capture system audio."""


@dataclass(frozen=True, slots=True)
class AudioChunk:
    samples: Float32Array
    """Mono float32 samples in [-1, 1] at ``TARGET_SAMPLE_RATE``."""
    start: float
    """Offset in seconds from capture start."""

    @property
    def duration(self) -> float:
        return len(self.samples) / TARGET_SAMPLE_RATE

    @property
    def end(self) -> float:
        return self.start + self.duration


_Item = AudioChunk | BaseException | None


class AudioCapture(ABC):
    name: ClassVar[str]

    def __init__(
        self,
        *,
        max_queue_seconds: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._max_queue_samples = int(max_queue_seconds * TARGET_SAMPLE_RATE)
        self._log = structlog.get_logger(__name__).bind(capture=self.name)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._items: deque[_Item] = deque()
        self._ready = asyncio.Event()
        self._queued_samples = 0
        self._resampler: Resampler | None = None
        self._started_at: float | None = None
        self._next_start = 0.0
        self._opened = False
        self._active = False
        self._finished = False

    @abstractmethod
    async def _open(self) -> None:
        """Start the native stream; it must begin calling ``_push()``."""

    @abstractmethod
    async def _close(self) -> None:
        """Stop the native stream; no ``_push()`` calls may happen after this returns."""

    @property
    def running(self) -> bool:
        return self._opened

    async def start(self) -> None:
        if self._opened:
            raise CaptureError("Audio capture is already running.")
        self._loop = asyncio.get_running_loop()
        self._items.clear()
        self._ready = asyncio.Event()
        self._queued_samples = 0
        self._resampler = None
        self._started_at = None
        self._next_start = 0.0
        self._finished = False
        self._active = True
        try:
            await self._open()
        except CaptureError:
            self._active = False
            raise
        except Exception as err:
            self._active = False
            raise CaptureError(f"Could not start audio capture ({self.name}): {err}") from err
        self._opened = True
        self._log.info("capture.started")

    async def stop(self) -> None:
        if not self._opened:
            return
        self._opened = False
        self._active = False
        try:
            await self._close()
        finally:
            # Chunks the native thread posted before _close() returned are already scheduled;
            # call_soon runs after them, so the tail of the recording isn't dropped.
            assert self._loop is not None
            finished = self._loop.create_future()

            def finish() -> None:
                self._finish_stream()
                finished.set_result(None)

            self._loop.call_soon(finish)
            await finished
            self._log.info("capture.stopped")

    async def stream(self) -> AsyncIterator[AudioChunk]:
        """Yield chunks until the capture stops; raises CaptureError if the backend fails."""
        if self._loop is None:
            raise CaptureError("Audio capture has not been started.")
        while True:
            while not self._items:
                self._ready.clear()
                await self._ready.wait()
            item = self._items.popleft()
            if item is None:
                return
            if isinstance(item, BaseException):
                raise item
            self._queued_samples -= len(item.samples)
            yield item

    # --- called from the backend's native thread -------------------------------------------

    def _push(self, frames: Float32Array, sample_rate: int) -> None:
        """Accept ``(frames, channels)`` or 1-D float32 audio at ``sample_rate``."""
        n_in = len(frames)
        if not self._active or n_in == 0:
            return
        now = self._clock()
        if self._resampler is None or self._resampler.in_rate != sample_rate:
            self._resampler = Resampler(sample_rate)
        out = self._resampler.process(to_mono(frames))

        in_duration = n_in / sample_rate
        if self._started_at is None:
            self._started_at = now - in_duration
        wall_start = now - self._started_at - in_duration
        if wall_start - self._next_start > GAP_THRESHOLD_SECONDS:
            self._next_start = wall_start
        start = self._next_start
        self._next_start += len(out) / TARGET_SAMPLE_RATE
        if len(out):
            self._post(AudioChunk(samples=out, start=start))

    def _fail(self, err: BaseException) -> None:
        if not isinstance(err, CaptureError):
            err = CaptureError(f"Audio capture ({self.name}) failed: {err}")
        self._post(err)

    def _end_of_stream(self) -> None:
        """The source has no more audio (e.g. end of file)."""
        self._active = False
        self._call_on_loop(self._finish_stream)

    def _backlog_seconds(self) -> float:
        return self._queued_samples / TARGET_SAMPLE_RATE

    # --- internals ------------------------------------------------------------------------

    def _post(self, item: _Item) -> None:
        self._call_on_loop(lambda: self._enqueue(item))

    def _call_on_loop(self, fn: Callable[[], None]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        # The loop may shut down between the check and the call.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(fn)

    def _enqueue(self, item: _Item) -> None:
        if self._finished:
            return
        if isinstance(item, AudioChunk):
            dropped = 0.0
            while (
                self._items
                and self._queued_samples + len(item.samples) > self._max_queue_samples
                and isinstance(self._items[0], AudioChunk)
            ):
                old = self._items.popleft()
                assert isinstance(old, AudioChunk)
                self._queued_samples -= len(old.samples)
                dropped += old.duration
            if dropped:
                self._log.warning("capture.backlog_dropped", seconds=round(dropped, 2))
            self._queued_samples += len(item.samples)
        self._items.append(item)
        self._ready.set()

    def _finish_stream(self) -> None:
        if self._finished:
            return
        if self._resampler is not None:
            tail = self._resampler.flush()
            if len(tail):
                self._enqueue(AudioChunk(samples=tail, start=self._next_start))
                self._next_start += len(tail) / TARGET_SAMPLE_RATE
        self._enqueue(None)
        self._finished = True
