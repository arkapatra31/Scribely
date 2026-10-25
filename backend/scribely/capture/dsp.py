"""Sample-format conversion and resampling to the STT input format."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import soxr

TARGET_SAMPLE_RATE = 16_000  # faster-whisper expects 16 kHz mono float32

Float32Array = npt.NDArray[np.float32]


def to_mono(frames: Float32Array) -> Float32Array:
    """Average channels of a ``(frames, channels)`` array; 1-D input is returned as is."""
    if frames.ndim == 1:
        return frames
    return frames.mean(axis=1, dtype=np.float32)


def int16_to_float32(data: bytes, channels: int) -> Float32Array:
    """Interleaved little-endian int16 PCM -> ``(frames, channels)`` float32 in [-1, 1)."""
    samples = np.frombuffer(data, dtype="<i2")
    usable = len(samples) - len(samples) % channels
    return (samples[:usable].reshape(-1, channels) / 32768.0).astype(np.float32)


def planar_float32_to_frames(data: bytes, channels: int, frames: int) -> Float32Array:
    """Non-interleaved float32 PCM (one block per channel) -> ``(frames, channels)``."""
    samples = np.frombuffer(data, dtype="<f4", count=channels * frames)
    return np.ascontiguousarray(samples.reshape(channels, frames).T)


class Resampler:
    """Streaming mono resampler to ``TARGET_SAMPLE_RATE`` that keeps filter state across chunks."""

    def __init__(self, in_rate: int, out_rate: int = TARGET_SAMPLE_RATE) -> None:
        self.in_rate = in_rate
        self._stream = (
            None if in_rate == out_rate else soxr.ResampleStream(in_rate, out_rate, 1, "float32")
        )

    def process(self, mono: Float32Array) -> Float32Array:
        if self._stream is None:
            return mono
        out: Float32Array = self._stream.resample_chunk(mono)
        return out

    def flush(self) -> Float32Array:
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        out: Float32Array = self._stream.resample_chunk(np.zeros(0, dtype=np.float32), last=True)
        return out
