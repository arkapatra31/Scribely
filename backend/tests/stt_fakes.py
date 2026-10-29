"""Deterministic stand-ins for the VAD and Whisper, plus synthetic audio."""

from typing import Any

import numpy as np

from scribely.capture.dsp import TARGET_SAMPLE_RATE as SR
from scribely.capture.dsp import Float32Array
from scribely.config import SttConfig
from scribely.stt.transcriber import LoadProgress, TimedText


class EnergyVAD:
    """Deterministic stand-in for Silero: 10 ms windows with RMS > 0.05 are speech."""

    win = SR // 100

    def speech_spans(self, audio: Float32Array) -> list[tuple[int, int]]:
        n = len(audio) // self.win
        if n == 0:
            return []
        rms = np.sqrt(np.mean(audio[: n * self.win].reshape(n, self.win) ** 2, axis=1))
        spans: list[tuple[int, int]] = []
        for i in np.flatnonzero(rms > 0.05):
            start, end = int(i) * self.win, (int(i) + 1) * self.win
            if spans and start - spans[-1][1] <= 10 * self.win:  # merge gaps < 100 ms
                spans[-1] = (spans[-1][0], end)
            else:
                spans.append((start, end))
        return spans


class FakeTranscriber:
    """Reports the length of the speech it was given, e.g. "speech 2.0s"."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def transcribe(
        self, audio: Float32Array, *, final: bool, prompt: str | None = None
    ) -> list[TimedText]:
        self.calls.append({"final": final, "prompt": prompt, "seconds": len(audio) / SR})
        voiced = sum(end - start for start, end in EnergyVAD().speech_spans(audio))
        if voiced == 0:
            return []
        return [TimedText(0.0, len(audio) / SR, f"speech {voiced / SR:.1f}s")]


def tone(seconds: float) -> Float32Array:
    t = np.arange(int(seconds * SR)) / SR
    return (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def quiet(seconds: float) -> Float32Array:
    return np.zeros(int(seconds * SR), dtype=np.float32)


class LoadableFakeTranscriber(FakeTranscriber):
    def __init__(self, load_error: Exception | None = None) -> None:
        super().__init__()
        self.load_error = load_error
        self.loads = 0
        self.configs: list[SttConfig] = []

    def load(self, on_progress: LoadProgress | None = None) -> None:
        self.loads += 1
        if on_progress is not None:
            on_progress("loading", None)
        if self.load_error is not None:
            raise self.load_error

    def configure(self, cfg: SttConfig) -> None:
        self.configs.append(cfg)
