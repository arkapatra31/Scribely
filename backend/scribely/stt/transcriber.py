"""faster-whisper wrapper: transcribe one block of 16 kHz mono audio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scribely.capture.dsp import Float32Array
from scribely.config import SttConfig


class STTError(Exception):
    """Speech-to-text problem with a plain-language message safe to show the user."""


@dataclass(frozen=True, slots=True)
class TimedText:
    start: float
    """Seconds from the start of the transcribed block."""
    end: float
    text: str


class Transcriber(Protocol):
    def transcribe(
        self, audio: Float32Array, *, final: bool, prompt: str | None = None
    ) -> list[TimedText]:
        """Blocking. ``final=False`` asks for a fast, rough pass (live partials)."""
        ...


class WhisperTranscriber:
    def __init__(self, cfg: SttConfig, models_dir: Path) -> None:
        self._cfg = cfg
        self._models_dir = models_dir
        self._model: Any = None

    def load(self) -> None:
        """Blocking; downloads the model into ``models_dir`` on first use."""
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        name = self._cfg.model
        try:
            self._model = WhisperModel(
                name,
                device=self._cfg.device,
                compute_type=self._cfg.compute_type,
                download_root=str(self._models_dir),
            )
        except Exception as err:
            if "Invalid model size" in str(err):
                raise STTError(
                    f'Unknown speech model "{name}". Use a size such as tiny, base, small, '
                    "medium or large-v3, or the path to a CTranslate2 model folder."
                ) from None
            if self._cfg.device == "cuda" or "CUDA" in str(err):
                raise STTError(
                    f'Couldn\'t load speech model "{name}" on the GPU ({err}). '
                    'Set device = "cpu" under [stt] in config.toml.'
                ) from None
            raise STTError(
                f'Couldn\'t load speech model "{name}": {err}. The first run downloads it to '
                f"{self._models_dir}; check your internet connection, or point [stt] model at "
                "a local model folder."
            ) from None

    def transcribe(
        self, audio: Float32Array, *, final: bool, prompt: str | None = None
    ) -> list[TimedText]:
        if self._model is None:
            raise STTError("The speech model is not loaded yet.")
        segments, _info = self._model.transcribe(
            audio,
            language=self._cfg.language,
            beam_size=self._cfg.beam_size if final else 1,
            temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0) if final else 0.0,
            vad_filter=False,  # the streaming layer already cut this block at speech
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            without_timestamps=False,
        )
        out: list[TimedText] = []
        for seg in segments:  # lazy generator: decoding happens here
            text = seg.text.strip()
            if not text or (seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0):
                continue
            out.append(TimedText(start=float(seg.start), end=float(seg.end), text=text))
        return out
