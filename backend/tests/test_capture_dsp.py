import numpy as np

from scribely.capture.dsp import (
    TARGET_SAMPLE_RATE,
    Resampler,
    int16_to_float32,
    planar_float32_to_frames,
    to_mono,
)
from tests.audio import dominant_frequency, sine


def test_to_mono_averages_channels() -> None:
    frames = np.array([[1.0, 0.0], [0.5, 0.5]], dtype=np.float32)
    assert to_mono(frames).tolist() == [0.5, 0.5]
    assert to_mono(frames).dtype == np.float32


def test_int16_to_float32_scales_and_drops_partial_frame() -> None:
    data = np.array([0, 16384, -32768, 32767, 1], dtype="<i2").tobytes()
    frames = int16_to_float32(data, channels=2)
    assert frames.shape == (2, 2)
    assert frames[0].tolist() == [0.0, 0.5]
    assert frames[1, 0] == -1.0


def test_planar_to_frames() -> None:
    planar = np.array([1, 2, 3, 10, 20, 30], dtype="<f4").tobytes()
    frames = planar_float32_to_frames(planar, channels=2, frames=3)
    assert frames.tolist() == [[1, 10], [2, 20], [3, 30]]


def test_resampler_streams_48k_to_16k_preserving_pitch() -> None:
    audio = sine(440, 1.0, 48_000)
    resampler = Resampler(48_000)
    parts = [resampler.process(block) for block in np.array_split(audio, 37)]
    parts.append(resampler.flush())
    out = np.concatenate(parts)
    assert abs(len(out) - TARGET_SAMPLE_RATE) <= 2
    assert out.dtype == np.float32
    assert abs(dominant_frequency(out, TARGET_SAMPLE_RATE) - 440) < 2


def test_resampler_passthrough_at_target_rate() -> None:
    audio = sine(440, 0.1, TARGET_SAMPLE_RATE)
    resampler = Resampler(TARGET_SAMPLE_RATE)
    assert resampler.process(audio) is audio
    assert len(resampler.flush()) == 0
