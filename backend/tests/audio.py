"""Test helpers for generating audio."""

import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt


def sine(freq: float, seconds: float, rate: int, channels: int = 1) -> npt.NDArray[np.float32]:
    t = np.arange(int(seconds * rate)) / rate
    mono = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return mono if channels == 1 else np.repeat(mono[:, None], channels, axis=1)


def write_wav(path: Path, frames: npt.NDArray[np.float32], rate: int) -> Path:
    channels = 1 if frames.ndim == 1 else frames.shape[1]
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((frames * 32767).astype("<i2").tobytes())
    return path


def dominant_frequency(samples: npt.NDArray[np.float32], rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(samples))
    return float(np.fft.rfftfreq(len(samples), 1 / rate)[int(np.argmax(spectrum))])
