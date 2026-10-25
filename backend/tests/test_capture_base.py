import asyncio
import itertools
import threading
from typing import Any

import numpy as np
import pytest

from scribely.capture.base import AudioCapture, AudioChunk, CaptureError
from scribely.capture.dsp import TARGET_SAMPLE_RATE
from tests.audio import sine


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeCapture(AudioCapture):
    name = "fake"

    def __init__(self, open_error: Exception | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.open_error = open_error
        self.closed = False

    async def _open(self) -> None:
        if self.open_error is not None:
            raise self.open_error

    async def _close(self) -> None:
        self.closed = True

    def push_from_thread(self, frames: Any, rate: int) -> None:
        t = threading.Thread(target=self._push, args=(frames, rate))
        t.start()
        t.join()


async def collect(capture: AudioCapture) -> list[AudioChunk]:
    return [chunk async for chunk in capture.stream()]


def test_chunks_are_16k_mono_with_contiguous_offsets() -> None:
    async def run() -> list[AudioChunk]:
        clock = FakeClock()
        cap = FakeCapture(clock=clock)
        await cap.start()
        for _ in range(5):
            clock.now += 0.1
            cap.push_from_thread(sine(440, 0.1, 48_000, channels=2), 48_000)
        await cap.stop()
        return await collect(cap)

    chunks = asyncio.run(run())
    assert all(c.samples.ndim == 1 and c.samples.dtype == np.float32 for c in chunks)
    total = sum(len(c.samples) for c in chunks)
    assert abs(total - int(0.5 * TARGET_SAMPLE_RATE)) <= 2
    for prev, cur in itertools.pairwise(chunks):
        assert cur.start == pytest.approx(prev.end)
    assert chunks[0].start == 0.0


def test_silence_gap_reanchors_offsets_to_wall_clock() -> None:
    async def run() -> list[AudioChunk]:
        clock = FakeClock()
        cap = FakeCapture(clock=clock)
        await cap.start()
        clock.now += 1.0
        cap.push_from_thread(sine(440, 1.0, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE)
        clock.now += 6.0  # 5 s with no callbacks, then 1 s of audio
        cap.push_from_thread(sine(440, 1.0, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE)
        await cap.stop()
        return await collect(cap)

    first, second = asyncio.run(run())
    assert first.start == 0.0
    assert second.start == pytest.approx(6.0)


def test_backend_failure_surfaces_as_capture_error() -> None:
    async def run() -> None:
        cap = FakeCapture()
        await cap.start()
        cap._fail(RuntimeError("device unplugged"))
        await collect(cap)

    with pytest.raises(CaptureError, match="device unplugged"):
        asyncio.run(run())


def test_open_failure_is_wrapped() -> None:
    async def run() -> None:
        await FakeCapture(open_error=OSError("boom")).start()

    with pytest.raises(CaptureError, match=r"Could not start audio capture \(fake\): boom"):
        asyncio.run(run())


def test_double_start_and_unstarted_stream_are_rejected() -> None:
    async def run() -> None:
        cap = FakeCapture()
        with pytest.raises(CaptureError, match="not been started"):
            await collect(cap)
        await cap.start()
        with pytest.raises(CaptureError, match="already running"):
            await cap.start()
        await cap.stop()
        assert cap.closed

    asyncio.run(run())


def test_backlog_drops_oldest_audio() -> None:
    async def run() -> list[AudioChunk]:
        clock = FakeClock()
        cap = FakeCapture(clock=clock, max_queue_seconds=1.0)
        await cap.start()
        for _ in range(3):
            clock.now += 0.6
            cap.push_from_thread(sine(440, 0.6, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE)
        await cap.stop()
        return await collect(cap)

    chunks = asyncio.run(run())
    assert len(chunks) == 1
    assert chunks[0].start == pytest.approx(1.2)


def test_pushes_after_stop_are_ignored() -> None:
    async def run() -> list[AudioChunk]:
        cap = FakeCapture()
        await cap.start()
        await cap.stop()
        cap.push_from_thread(sine(440, 0.1, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE)
        await asyncio.sleep(0)
        return await collect(cap)

    assert asyncio.run(run()) == []
