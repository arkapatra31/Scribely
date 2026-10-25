from pathlib import Path

import numpy as np
import pytest

from scribely.config import SttConfig
from scribely.stt import SileroVAD, STTError, WhisperTranscriber


def test_unknown_model_size_is_actionable(tmp_path: Path) -> None:
    transcriber = WhisperTranscriber(SttConfig(model="gigantic"), tmp_path)
    with pytest.raises(STTError, match='Unknown speech model "gigantic"'):
        transcriber.load()


def test_transcribe_before_load_is_reported(tmp_path: Path) -> None:
    with pytest.raises(STTError, match="not loaded"):
        WhisperTranscriber(SttConfig(), tmp_path).transcribe(
            np.zeros(16_000, dtype=np.float32), final=True
        )


def test_silero_vad_finds_no_speech_in_silence_or_tone() -> None:
    vad = SileroVAD()
    assert vad.speech_spans(np.zeros(32_000, dtype=np.float32)) == []
    t = np.arange(32_000) / 16_000
    assert vad.speech_spans((0.3 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)) == []


def test_huggingface_telemetry_disabled() -> None:
    import os

    import huggingface_hub.constants

    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"
    assert huggingface_hub.constants.HF_HUB_DISABLE_TELEMETRY is True
