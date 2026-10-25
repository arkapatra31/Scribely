"""Live speech-to-text: faster-whisper + Silero VAD over the capture stream."""

import os

# No telemetry (CLAUDE.md rule 4): faster-whisper fetches models via huggingface_hub, which
# reads this before import.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from scribely.stt.stream import StreamingTranscriber, Utterance
from scribely.stt.transcriber import STTError, TimedText, Transcriber, WhisperTranscriber
from scribely.stt.vad import SileroVAD, SpeechDetector

__all__ = [
    "STTError",
    "SileroVAD",
    "SpeechDetector",
    "StreamingTranscriber",
    "TimedText",
    "Transcriber",
    "Utterance",
    "WhisperTranscriber",
]
