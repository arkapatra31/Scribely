from pathlib import Path

import pytest

from scribely.config import ConfigError, Settings, find_config_file, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_without_config_file() -> None:
    settings = load_settings()
    assert settings.llm.provider == "azure_openai"
    assert settings.llm.model == "gpt-4o"
    assert settings.server.host == "127.0.0.1"


def test_example_config_matches_defaults() -> None:
    # Guards against config.toml.example drifting from the built-in defaults.
    assert load_settings(REPO_ROOT / "config.toml.example") == Settings()


def test_file_overrides_defaults(tmp_path: Path) -> None:
    path = write(tmp_path / "c.toml", '[llm]\nprovider = "anthropic"\nmodel = "claude-x"\n')
    settings = load_settings(path)
    assert settings.llm.provider == "anthropic"
    assert settings.llm.model == "claude-x"
    assert settings.llm.temperature == 0.2


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path / "c.toml", '[llm]\nprovider = "anthropic"\nmodel = "a"\n')
    monkeypatch.setenv("SCRIBELY_LLM__MODEL", "b")
    monkeypatch.setenv("SCRIBELY_SERVER__PORT", "9000")
    settings = load_settings(path)
    assert settings.llm.provider == "anthropic"
    assert settings.llm.model == "b"
    assert settings.server.port == 9000


def test_invalid_provider_is_actionable(tmp_path: Path) -> None:
    path = write(tmp_path / "c.toml", '[llm]\nprovider = "azure"\n')
    with pytest.raises(ConfigError) as exc:
        load_settings(path)
    msg = str(exc.value)
    assert "llm.provider" in msg
    assert "azure_openai" in msg


def test_unknown_key_is_reported(tmp_path: Path) -> None:
    path = write(tmp_path / "c.toml", '[llm]\nmodle = "x"\n')
    with pytest.raises(ConfigError, match=r"llm\.modle: unknown setting"):
        load_settings(path)


def test_bad_toml_is_reported(tmp_path: Path) -> None:
    path = write(tmp_path / "c.toml", "[llm\n")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_settings(path)


def test_overlap_must_be_smaller_than_chunk(tmp_path: Path) -> None:
    path = write(
        tmp_path / "c.toml", "[pipeline]\nchunk_size_tokens = 100\nchunk_overlap_tokens = 100\n"
    )
    with pytest.raises(ConfigError, match="chunk_overlap_tokens"):
        load_settings(path)


def test_lookup_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert find_config_file() is None
    user = write(tmp_path / "user-config" / "config.toml", "")
    assert find_config_file() == user
    cwd = write(tmp_path / "config.toml", "")
    assert find_config_file() == cwd
    explicit = write(tmp_path / "explicit.toml", "")
    monkeypatch.setenv("SCRIBELY_CONFIG", str(explicit))
    assert find_config_file() == explicit


def test_missing_explicit_config_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCRIBELY_CONFIG", str(tmp_path / "nope.toml"))
    with pytest.raises(ConfigError, match="no file exists there"):
        load_settings()


def test_paths_resolve(tmp_path: Path) -> None:
    path = write(tmp_path / "c.toml", f'[paths]\ndata_dir = "{tmp_path.as_posix()}/data"\n')
    paths = load_settings(path).paths
    assert paths.resolved_data_dir() == tmp_path / "data"
    assert paths.resolved_exports_dir() == tmp_path / "data" / "exports"
