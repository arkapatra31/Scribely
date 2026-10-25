import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_config_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's real env vars and config files out of tests."""
    for key in list(os.environ):
        if key.startswith("SCRIBELY_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")  # fake LLMs; never a real call
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "scribely.config.user_config_path", lambda *a, **k: tmp_path / "user-config"
    )
