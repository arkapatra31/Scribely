"""Speech models and languages offered in the app, and downloading a model with progress."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scribely.stt.transcriber import STTError

# Files faster-whisper needs (see faster_whisper.utils.download_model).
_ALLOW_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]
POLL_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class SpeechModelInfo:
    name: str
    label: str
    size_mb: int
    """Approximate download size."""
    description: str
    english_only: bool = False


SPEECH_MODELS: list[SpeechModelInfo] = [
    SpeechModelInfo("tiny", "Tiny", 75, "Fastest, least accurate. For slow computers."),
    SpeechModelInfo("base", "Base", 145, "Fast, a little rough."),
    SpeechModelInfo("small", "Small", 484, "Good balance of speed and accuracy. Recommended."),
    SpeechModelInfo("medium", "Medium", 1530, "More accurate; needs a fast computer."),
    SpeechModelInfo(
        "large-v3-turbo", "Large v3 Turbo", 1620, "Near-best accuracy; needs a fast computer."
    ),
    SpeechModelInfo("large-v3", "Large v3", 3090, "Most accurate and slowest."),
    SpeechModelInfo(
        "distil-large-v3",
        "Distil Large v3",
        1510,
        "Accurate and quick, English only.",
        english_only=True,
    ),
]

# Languages Whisper can transcribe (code -> English name).
# fmt: off
LANGUAGES: dict[str, str] = {
    "en": "English", "zh": "Chinese", "de": "German", "es": "Spanish", "ru": "Russian",
    "ko": "Korean", "fr": "French", "ja": "Japanese", "pt": "Portuguese", "tr": "Turkish",
    "pl": "Polish", "ca": "Catalan", "nl": "Dutch", "ar": "Arabic", "sv": "Swedish",
    "it": "Italian", "id": "Indonesian", "hi": "Hindi", "fi": "Finnish", "vi": "Vietnamese",
    "he": "Hebrew", "uk": "Ukrainian", "el": "Greek", "ms": "Malay", "cs": "Czech",
    "ro": "Romanian", "da": "Danish", "hu": "Hungarian", "ta": "Tamil", "no": "Norwegian",
    "th": "Thai", "ur": "Urdu", "hr": "Croatian", "bg": "Bulgarian", "lt": "Lithuanian",
    "la": "Latin", "mi": "Maori", "ml": "Malayalam", "cy": "Welsh", "sk": "Slovak",
    "te": "Telugu", "fa": "Persian", "lv": "Latvian", "bn": "Bengali", "sr": "Serbian",
    "az": "Azerbaijani", "sl": "Slovenian", "kn": "Kannada", "et": "Estonian",
    "mk": "Macedonian", "br": "Breton", "eu": "Basque", "is": "Icelandic", "hy": "Armenian",
    "ne": "Nepali", "mn": "Mongolian", "bs": "Bosnian", "kk": "Kazakh", "sq": "Albanian",
    "sw": "Swahili", "gl": "Galician", "mr": "Marathi", "pa": "Punjabi", "si": "Sinhala",
    "km": "Khmer", "sn": "Shona", "yo": "Yoruba", "so": "Somali", "af": "Afrikaans",
    "oc": "Occitan", "ka": "Georgian", "be": "Belarusian", "tg": "Tajik", "sd": "Sindhi",
    "gu": "Gujarati", "am": "Amharic", "yi": "Yiddish", "lo": "Lao", "uz": "Uzbek",
    "fo": "Faroese", "ht": "Haitian Creole", "ps": "Pashto", "tk": "Turkmen", "nn": "Nynorsk",
    "mt": "Maltese", "sa": "Sanskrit", "lb": "Luxembourgish", "my": "Myanmar",
    "bo": "Tibetan", "tl": "Tagalog", "mg": "Malagasy", "as": "Assamese", "tt": "Tatar",
    "haw": "Hawaiian", "ln": "Lingala", "ha": "Hausa", "ba": "Bashkir", "jw": "Javanese",
    "su": "Sundanese", "yue": "Cantonese",
}
# fmt: on


def is_english_only(name: str) -> bool:
    return name.endswith(".en") or any(m.english_only for m in SPEECH_MODELS if m.name == name)


def repo_id(name: str) -> str | None:
    """The Hugging Face repo for a model size or repo id; None for unknown names."""
    if "/" in name:
        return name
    from faster_whisper.utils import _MODELS

    found: str | None = _MODELS.get(name)
    return found


def is_downloaded(name: str, models_dir: Path) -> bool:
    """Whether the model can load without the internet (a local folder, or in the cache)."""
    if Path(name).expanduser().is_dir():
        return True
    if repo_id(name) is None:
        return False
    from faster_whisper.utils import download_model

    try:
        download_model(name, cache_dir=str(models_dir), local_files_only=True)
    except Exception:
        return False
    return True


def download(name: str, models_dir: Path, on_progress: Callable[[float | None], None]) -> None:
    """Blocking. Downloads ``name`` into ``models_dir``, reporting 0..1 (None if unknown)."""
    repo = repo_id(name)
    if repo is None:
        raise STTError(
            f'Unknown speech model "{name}". Pick one in Settings → Speech, or point [stt] '
            "model at a local CTranslate2 model folder."
        )
    total = _total_bytes(repo)
    folder = models_dir / f"models--{repo.replace('/', '--')}"
    done = threading.Event()

    def poll() -> None:
        while not done.wait(POLL_SECONDS):
            on_progress(min(_dir_bytes(folder) / total, 1.0) if total else None)

    poller = threading.Thread(target=poll, name="scribely-model-download", daemon=True)
    on_progress(0.0 if total else None)
    poller.start()
    try:
        from faster_whisper.utils import download_model

        download_model(name, cache_dir=str(models_dir))
    except Exception as err:
        raise STTError(
            f'Couldn\'t download the speech model "{name}": {err}. Check your internet '
            "connection and try again."
        ) from None
    finally:
        done.set()
        poller.join()
    on_progress(1.0)


def _total_bytes(repo: str) -> int | None:
    import fnmatch

    from huggingface_hub import HfApi

    try:
        info = HfApi().model_info(repo, files_metadata=True)
    except Exception:
        return None  # progress is unknown, the download itself may still work
    total = sum(
        s.size or 0
        for s in info.siblings or []
        if any(fnmatch.fnmatch(s.rfilename, p) for p in _ALLOW_PATTERNS)
    )
    return total or None


def _dir_bytes(folder: Path) -> int:
    """Bytes under ``folder``, counting partial downloads, not counting symlinks twice."""
    total = 0
    for path in folder.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total
