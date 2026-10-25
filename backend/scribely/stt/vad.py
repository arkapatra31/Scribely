"""Voice activity detection with the Silero model bundled in faster-whisper."""

from __future__ import annotations

from typing import Protocol

from scribely.capture.dsp import TARGET_SAMPLE_RATE, Float32Array

# Spans separated by less than this are merged by the VAD itself; the streaming layer
# decides separately (min_silence_ms) when a pause ends a segment.
_VAD_MERGE_SILENCE_MS = 100


class SpeechDetector(Protocol):
    def speech_spans(self, audio: Float32Array) -> list[tuple[int, int]]:
        """Blocking. ``(start, end)`` sample indices of speech in 16 kHz mono audio."""
        ...


class SileroVAD:
    def __init__(self, threshold: float = 0.5) -> None:
        from faster_whisper.vad import VadOptions

        self._options = VadOptions(
            threshold=threshold,
            min_speech_duration_ms=250,
            min_silence_duration_ms=_VAD_MERGE_SILENCE_MS,
            speech_pad_ms=0,
        )

    def speech_spans(self, audio: Float32Array) -> list[tuple[int, int]]:
        from faster_whisper.vad import get_speech_timestamps

        stamps = get_speech_timestamps(audio, self._options, sampling_rate=TARGET_SAMPLE_RATE)
        return [(int(s["start"]), int(s["end"])) for s in stamps]
