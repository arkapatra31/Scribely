"""Configuration: defaults < config.toml < SCRIBELY_* environment variables.

The config file is looked up in this order:
1. the path in the ``SCRIBELY_CONFIG`` environment variable,
2. ``config.toml`` in the current working directory,
3. ``config.toml`` in the per-user config dir (via ``platformdirs``).

If none exists, built-in defaults are used. Provider API keys are never read
from the config file; LLM SDKs pick them up from their standard environment
variables (e.g. ``AZURE_OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal, Self

from platformdirs import user_config_path, user_data_path
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

APP_NAME = "Scribely"
CONFIG_ENV_VAR = "SCRIBELY_CONFIG"
CONFIG_FILENAME = "config.toml"

LLMProvider = Literal["azure_openai", "anthropic", "openai", "gemini", "ollama"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
CaptureBackend = Literal["auto", "wasapi", "screencapturekit", "file"]


class ConfigError(Exception):
    """Configuration problem with a plain-language message safe to show the user."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServerConfig(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)


class CaptureConfig(_Section):
    # "auto" picks wasapi on Windows and screencapturekit on macOS.
    backend: CaptureBackend = "auto"
    # WAV file streamed by the "file" backend (development/testing).
    file_path: Path | None = None
    file_realtime: bool = True
    # Audio buffered for a slow consumer before the oldest is dropped.
    max_queue_seconds: float = Field(default=120.0, gt=0)

    @model_validator(mode="after")
    def _file_backend_needs_path(self) -> Self:
        if self.backend == "file" and self.file_path is None:
            raise ValueError('backend = "file" requires file_path')
        return self


class SttConfig(_Section):
    # A faster-whisper size (tiny, base, small, medium, large-v3, distil-large-v3, ...),
    # a Hugging Face repo id, or a local CTranslate2 model folder.
    model: str = Field(default="small", min_length=1)
    device: Literal["auto", "cpu", "cuda"] = "auto"
    # CTranslate2 compute type, e.g. int8 or float16; "default" lets it choose per device.
    compute_type: str = "default"
    # Spoken language code such as "en"; None auto-detects per segment.
    language: str | None = None
    beam_size: int = Field(default=5, ge=1)
    vad_threshold: float = Field(default=0.5, gt=0.0, lt=1.0)
    # A pause this long ends a transcript segment.
    min_silence_ms: int = Field(default=600, ge=100)
    speech_pad_ms: int = Field(default=200, ge=0)
    # Continuous speech is cut (at the longest pause) once a segment reaches this length.
    max_segment_seconds: float = Field(default=15.0, ge=2.0)
    # How often to emit live partial hypotheses while someone is speaking; 0 disables.
    partial_interval_seconds: float = Field(default=1.0, ge=0.0)


class LLMConfig(_Section):
    provider: LLMProvider = "azure_openai"
    model: str = Field(default="gpt-4o", min_length=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    # Overrides the model's known context window (tokens); None means use the built-in value.
    context_window: int | None = Field(default=None, gt=0)
    azure_endpoint: str | None = None
    azure_deployment: str | None = None
    azure_api_version: str = "2024-10-21"
    ollama_host: str = "http://localhost:11434"


class PipelineConfig(_Section):
    chunk_size_tokens: int = Field(default=6000, gt=0)
    chunk_overlap_tokens: int = Field(default=200, ge=0)

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> Self:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")
        return self


class PathsConfig(_Section):
    data_dir: Path | None = None
    exports_dir: Path | None = None
    models_dir: Path | None = None

    def resolved_data_dir(self) -> Path:
        if self.data_dir is not None:
            return self.data_dir.expanduser()
        return user_data_path(APP_NAME, appauthor=False)

    def resolved_exports_dir(self) -> Path:
        if self.exports_dir is not None:
            return self.exports_dir.expanduser()
        return self.resolved_data_dir() / "exports"

    def resolved_models_dir(self) -> Path:
        if self.models_dir is not None:
            return self.models_dir.expanduser()
        return self.resolved_data_dir() / "models"


class LoggingConfig(_Section):
    level: LogLevel = "INFO"
    format: Literal["console", "json"] = "console"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCRIBELY_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    server: ServerConfig = ServerConfig()
    capture: CaptureConfig = CaptureConfig()
    stt: SttConfig = SttConfig()
    llm: LLMConfig = LLMConfig()
    pipeline: PipelineConfig = PipelineConfig()
    paths: PathsConfig = PathsConfig()
    logging: LoggingConfig = LoggingConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # load_settings() merges file + env itself so the precedence stays explicit.
        return (init_settings,)


def find_config_file() -> Path | None:
    if env_path := os.environ.get(CONFIG_ENV_VAR):
        path = Path(env_path).expanduser()
        if not path.is_file():
            raise ConfigError(f"{CONFIG_ENV_VAR} points to {path}, but no file exists there.")
        return path
    for candidate in (
        Path.cwd() / CONFIG_FILENAME,
        user_config_path(APP_NAME, appauthor=False) / CONFIG_FILENAME,
    ):
        if candidate.is_file():
            return candidate
    return None


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings, raising ConfigError with an actionable message on any problem."""
    path = config_path if config_path is not None else find_config_file()
    file_data = _read_toml(path) if path is not None else {}
    env_data = EnvSettingsSource(Settings)()
    source = f"{path} + environment" if path is not None else "defaults + environment"
    try:
        return Settings(**_deep_merge(file_data, env_data))
    except ValidationError as err:
        raise ConfigError(_format_validation_error(err, source)) from None


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"Config file {path} is not valid TOML: {err}") from None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _format_validation_error(err: ValidationError, source: str) -> str:
    lines = [f"Invalid configuration ({source}):"]
    for e in err.errors():
        loc = ".".join(str(part) for part in e["loc"]) or "<root>"
        msg = "unknown setting (check the spelling)" if e["type"] == "extra_forbidden" else e["msg"]
        lines.append(f"  - {loc}: {msg}")
    return "\n".join(lines)
