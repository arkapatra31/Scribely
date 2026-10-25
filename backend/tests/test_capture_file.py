import asyncio
import time
from pathlib import Path

import numpy as np
import pytest

from scribely.capture.base import AudioChunk, CaptureError
from scribely.capture.dsp import TARGET_SAMPLE_RATE
from scribely.capture.file import FileCapture
from tests.audio import dominant_frequency, sine, write_wav


async def capture_all(cap: FileCapture) -> list[AudioChunk]:
    await cap.start()
    chunks = [c async for c in cap.stream()]
    await cap.stop()
    return chunks


def test_streams_whole_file_as_16k_mono(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "a.wav", sine(440, 2.0, 44_100, channels=2), 44_100)
    chunks = asyncio.run(capture_all(FileCapture(path, realtime=False)))
    samples = np.concatenate([c.samples for c in chunks])
    assert abs(len(samples) - 2 * TARGET_SAMPLE_RATE) <= 2
    assert abs(dominant_frequency(samples, TARGET_SAMPLE_RATE) - 440) < 2
    assert chunks[-1].end == pytest.approx(2.0, abs=1e-3)


def test_realtime_paces_playback(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "a.wav", sine(440, 0.3, 16_000), 16_000)
    started = time.monotonic()
    asyncio.run(capture_all(FileCapture(path, realtime=True)))
    assert time.monotonic() - started >= 0.25


def test_stop_mid_file(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "a.wav", sine(440, 30.0, 16_000), 16_000)

    async def run() -> float:
        cap = FileCapture(path, realtime=True)
        await cap.start()
        await asyncio.sleep(0.2)
        await cap.stop()
        return sum(c.duration for c in [c async for c in cap.stream()])

    assert 0.1 < asyncio.run(run()) < 1.0


@pytest.mark.parametrize(
    ("content", "message"),
    [(None, "not found"), (b"not a wav", "not a readable WAV")],
)
def test_bad_files_are_reported(tmp_path: Path, content: bytes | None, message: str) -> None:
    path = tmp_path / "x.wav"
    if content is not None:
        path.write_bytes(content)
    with pytest.raises(CaptureError, match=message):
        asyncio.run(FileCapture(path).start())


def test_non_16_bit_wav_is_rejected(tmp_path: Path) -> None:
    import wave

    path = tmp_path / "x.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(8000)
        wav.writeframes(b"\x80" * 800)
    with pytest.raises(CaptureError, match="only 16-bit PCM"):
        asyncio.run(FileCapture(path).start())
