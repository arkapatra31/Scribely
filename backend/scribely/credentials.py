"""LLM API keys, held in memory only for the life of the backend process.

Keys are never written anywhere: not to config files, the database, the OS keychain, or
logs. The user enters the key in Settings each time Scribely starts; the provider's
standard environment variable is accepted as a fallback.
"""

from __future__ import annotations

import os

from scribely.config import LLMProvider
from scribely.models import KeySource

KEY_ENV: dict[str, str] = {
    "azure_openai": "AZURE_OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}


class Credentials:
    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    def get(self, provider: LLMProvider) -> str | None:
        """The key to use: one entered this session wins over the environment variable."""
        if provider not in KEY_ENV:
            return None
        return self._keys.get(provider) or os.environ.get(KEY_ENV[provider]) or None

    def source(self, provider: LLMProvider) -> KeySource:
        if provider not in KEY_ENV:
            return "not_needed"
        if provider in self._keys:
            return "session"
        return "env" if os.environ.get(KEY_ENV[provider]) else "missing"

    def set(self, provider: LLMProvider, key: str) -> None:
        self._keys[provider] = key

    def clear(self, provider: LLMProvider) -> None:
        self._keys.pop(provider, None)

    def __repr__(self) -> str:  # never print keys, even by accident
        return f"Credentials(providers={sorted(self._keys)})"
