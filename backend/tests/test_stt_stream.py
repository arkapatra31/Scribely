import asyncio
import itertools
from collections.abc import AsyncIterator, Callable
from typing import Any

import numpy as np
import pytest

from scribely.capture.base import AudioChunk
from scribely.capture.dsp import TARGET_SAMPLE_RATE as SR
from scribely.capture.dsp import Float32Array
from scribely.config import SttConfig
from scribely.stt.stream import StreamingTranscriber, Utterance
from tests.stt_fakes import EnergyVAD, FakeTranscriber, quiet, tone


async def chunked(
    audio: Float32Array, start: float = 0.0, size: float = 0.1
) -> AsyncIterator[AudioChunk]:
    step = int(size * SR)
    for i in range(0, len(audio), step):
        yield AudioChunk(samples=audio[i : i + step], start=start + i / SR)


async def inline(fn: Callable[..., Any], *args: Any) -> Any:
    return fn(*args)


class StepClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.25
        return self.now


def run(chunks: AsyncIterator[AudioChunk], **cfg: Any) -> tuple[list[Utterance], FakeTranscriber]:
    transcriber = FakeTranscriber()
    stream = StreamingTranscriber(
        transcriber,
        EnergyVAD(),
        SttConfig(**{"partial_interval_seconds": 0, **cfg}),
        run_blocking=inline,
        clock=StepClock(),
    )

    async def collect() -> list[Utterance]:
        return [u async for u in stream.run(chunks)]

    return asyncio.run(collect()), transcriber


def finals(utterances: list[Utterance]) -> list[Utterance]:
    return [u for u in utterances if u.final]


def test_pause_splits_speech_into_timestamped_segments() -> None:
    audio = np.concatenate([quiet(0.5), tone(2.0), quiet(1.0), tone(1.0), quiet(1.0)])
    out = finals(run(chunked(audio))[0])
    assert [u.text for u in out] == ["speech 2.0s", "speech 1.0s"]
    assert out[0].start == pytest.approx(0.5 - 0.2, abs=0.02)
    assert out[0].end == pytest.approx(2.5 + 0.2, abs=0.02)
    assert out[1].start == pytest.approx(3.5 - 0.2, abs=0.02)


def test_trailing_speech_is_flushed_at_end_of_stream() -> None:
    out = finals(run(chunked(np.concatenate([quiet(0.3), tone(1.2)])))[0])
    assert [u.text for u in out] == ["speech 1.2s"]


def test_continuous_speech_is_cut_at_max_segment_length() -> None:
    # 40 s of speech with a 0.3 s breath every 4 s (shorter than min_silence).
    parts = []
    for _ in range(10):
        parts += [tone(3.7), quiet(0.3)]
    out = finals(run(chunked(np.concatenate(parts)), max_segment_seconds=10.0)[0])
    assert len(out) >= 4
    assert all(u.end - u.start <= 10.5 for u in out)
    voiced = sum(float(u.text.split()[1][:-1]) for u in out)
    assert voiced == pytest.approx(37.0, abs=0.3)  # nothing lost or duplicated
    for a, b in itertools.pairwise(out):
        assert b.start >= a.end - 0.01


def test_long_unbroken_speech_is_hard_cut() -> None:
    out = finals(run(chunked(tone(25.0)), max_segment_seconds=10.0)[0])
    assert sum(float(u.text.split()[1][:-1]) for u in out) == pytest.approx(25.0, abs=0.1)
    assert max(u.end - u.start for u in out) <= 10.6


def test_silence_only_never_transcribes() -> None:
    utterances, transcriber = run(chunked(quiet(30.0)))
    assert utterances == []
    assert transcriber.calls == []


def test_timeline_gap_finalizes_buffered_speech() -> None:
    async def chunks() -> AsyncIterator[AudioChunk]:
        async for c in chunked(tone(1.0)):
            yield c
        async for c in chunked(np.concatenate([tone(1.0), quiet(1.0)]), start=10.0):
            yield c

    out = finals(run(chunks())[0])
    assert len(out) == 2
    assert out[0].end <= 1.01
    assert out[1].start == pytest.approx(10.0, abs=0.01)


def test_partials_precede_the_final_and_are_disabled_by_zero() -> None:
    audio = np.concatenate([tone(4.0), quiet(1.0)])
    utterances, transcriber = run(chunked(audio), partial_interval_seconds=1.0)
    partial_idx = [i for i, u in enumerate(utterances) if not u.final]
    final_idx = [i for i, u in enumerate(utterances) if u.final]
    assert partial_idx and final_idx and max(partial_idx) < min(final_idx)
    assert all(not c["final"] for c in transcriber.calls[:-1])

    utterances, _ = run(chunked(audio), partial_interval_seconds=0)
    assert all(u.final for u in utterances)


def test_previous_text_is_passed_as_prompt() -> None:
    audio = np.concatenate([tone(1.0), quiet(1.0), tone(1.0), quiet(1.0)])
    _, transcriber = run(chunked(audio))
    final_calls = [c for c in transcriber.calls if c["final"]]
    assert final_calls[0]["prompt"] == ""
    assert final_calls[1]["prompt"].strip() == "speech 1.0s"


def test_file_capture_feeds_streaming_transcriber(tmp_path: Any) -> None:
    from scribely.capture.file import FileCapture
    from tests.audio import write_wav

    audio = np.concatenate([quiet(0.5), tone(1.5), quiet(1.0), tone(0.8)])
    path = write_wav(tmp_path / "lecture.wav", np.repeat(audio[:, None], 2, axis=1), SR)
    capture = FileCapture(path, realtime=False)
    stream = StreamingTranscriber(
        FakeTranscriber(), EnergyVAD(), SttConfig(partial_interval_seconds=0)
    )

    async def go() -> list[Utterance]:
        await capture.start()
        out = [u async for u in stream.run(capture.stream())]
        await capture.stop()
        return out

    out = asyncio.run(go())
    assert [u.text for u in out] == ["speech 1.5s", "speech 0.8s"]
    assert out[1].start == pytest.approx(3.0 - 0.2, abs=0.02)
