import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from scribely.config import LLMConfig, Settings
from scribely.credentials import Credentials
from scribely.models import LlmSettings
from scribely.session import LiveSessionManager
from scribely.session.store import SessionStore
from tests.fake_llm import FakeLLM

SECRET = "sk-test-SECRET-123"


@pytest.fixture(autouse=True)
def _no_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("AZURE_OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def ok(schema: type[BaseModel], prompt: str) -> Any:
    return "OK"


def manager(db: Path, llm: FakeLLM | None = None) -> LiveSessionManager:
    fake = llm or FakeLLM(ok)
    return LiveSessionManager(
        Settings(llm=LLMConfig()),
        store=SessionStore.open(db),
        llm_factory=lambda cfg, key: fake.as_chat_model(),
        credentials=Credentials(),
    )


def azure(**kw: Any) -> LlmSettings:
    base = {
        "provider": "azure_openai",
        "model": "gpt-4o",
        "azure_endpoint": "https://me.openai.azure.com/",
        "azure_deployment": "notes",
        "azure_api_version": "2024-10-21",
        "ollama_host": "http://localhost:11434",
    }
    return LlmSettings(**{**base, **kw})


def test_credentials_session_key_wins_and_is_never_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    creds = Credentials()
    assert creds.source("azure_openai") == "missing" and creds.get("azure_openai") is None
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "from-env")
    assert creds.source("azure_openai") == "env" and creds.get("azure_openai") == "from-env"
    creds.set("azure_openai", SECRET)
    assert creds.source("azure_openai") == "session" and creds.get("azure_openai") == SECRET
    assert SECRET not in repr(creds)
    creds.clear("azure_openai")
    assert creds.get("azure_openai") == "from-env"
    assert creds.source("ollama") == "not_needed"


def test_saved_settings_survive_restart_but_the_key_does_not(tmp_path: Path) -> None:
    db = tmp_path / "scribely.db"

    async def first_run() -> tuple[str | None, str]:
        m = manager(db)
        await m.check_llm_setup()
        before = m._status().llm_issue
        await m.save_llm_settings(azure(model="gpt-4.1"), SECRET)
        message = await m.llm_settings_message()
        assert m._status().llm_issue is None
        return before, message.model_dump_json()

    async def second_run() -> tuple[str, str | None, str]:
        m = manager(db)
        await m.load_saved_llm_settings()
        await m.check_llm_setup()
        msg = await m.llm_settings_message()
        return msg.settings.model, m._status().llm_issue, msg.key_sources["azure_openai"]

    before, message_json = asyncio.run(first_run())
    assert before is not None
    assert SECRET not in message_json
    assert SECRET.encode() not in b"".join(p.read_bytes() for p in tmp_path.iterdir())

    model, issue, source = asyncio.run(second_run())
    assert model == "gpt-4.1"
    assert source == "missing"
    assert issue is not None and "No API key" in issue


def test_empty_key_forgets_and_none_keeps(tmp_path: Path) -> None:
    async def run() -> list[str]:
        m = manager(tmp_path / "scribely.db")
        await m.save_llm_settings(azure(), SECRET)
        await m.save_llm_settings(azure(model="gpt-4o-mini"), None)  # keep
        kept = (await m.llm_settings_message()).key_sources["azure_openai"]
        await m.save_llm_settings(azure(), "")  # forget
        gone = (await m.llm_settings_message()).key_sources["azure_openai"]
        return [kept, gone]

    assert asyncio.run(run()) == ["session", "missing"]


def test_connection_test_ok_and_failure(tmp_path: Path) -> None:
    class AuthenticationError(Exception):
        status_code = 401

    def rejected(schema: type[BaseModel], prompt: str) -> Any:
        raise AuthenticationError("bad key")

    async def run() -> tuple[Any, Any, Any]:
        good = manager(tmp_path / "a.db")
        missing = await good.test_llm()
        await good.save_llm_settings(azure(), SECRET)
        passed = await good.test_llm()
        bad = manager(tmp_path / "b.db", FakeLLM(rejected))
        await bad.save_llm_settings(azure(), "wrong")
        return missing, passed, await bad.test_llm()

    missing, passed, failed = asyncio.run(run())
    assert not missing.ok and "endpoint and deployment in Settings" in missing.message
    assert passed.ok and passed.message == "Connected to Azure OpenAI (gpt-4o)."
    assert not failed.ok and "rejected the API key" in failed.message


def test_settings_validation() -> None:
    with pytest.raises(ValueError, match="must start with https://"):
        azure(azure_endpoint="http://insecure.example")
    assert azure(azure_endpoint="  ", azure_deployment=" d ").azure_endpoint is None
    assert azure(azure_deployment=" d ").azure_deployment == "d"


def test_settings_over_websocket(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from scribely.api import create_app

    m = manager(Path(tempfile.mkdtemp()) / "scribely.db")
    with TestClient(create_app(Settings(), m)) as client, client.websocket_connect("/ws") as ws:
        for _ in range(3):
            ws.receive_text()

        def until(kind: str) -> dict[str, Any]:
            for _ in range(50):
                msg: dict[str, Any] = json.loads(ws.receive_text())
                if msg["type"] == kind:
                    return msg
            raise AssertionError(kind)

        ws.send_text(json.dumps({"type": "get_llm_settings"}))
        current = until("llm_settings")
        assert current["settings"]["provider"] == "azure_openai"
        assert current["suggested_models"]["anthropic"]

        bad = {**azure().model_dump(), "azure_endpoint": "http://nope"}
        ws.send_text(json.dumps({"type": "save_llm_settings", "settings": bad, "api_key": SECRET}))
        assert until("error")["message"] == "The Azure endpoint must start with https://"

        good = azure().model_dump()
        ws.send_text(json.dumps({"type": "save_llm_settings", "settings": good, "api_key": SECRET}))
        saved = until("llm_settings")
        assert saved["key_sources"]["azure_openai"] == "session"
        assert SECRET not in json.dumps(saved)
        assert until("status")["llm_issue"] is None

        ws.send_text(json.dumps({"type": "test_llm"}))
        assert until("llm_test")["ok"] is True


def test_settings_saved_by_older_versions_still_load(tmp_path: Path) -> None:
    db = tmp_path / "scribely.db"
    legacy = {**azure(model="gpt-4.1").model_dump(), "temperature": 0.2}

    async def run() -> tuple[str, float | None]:
        m = manager(db)
        await m._store.set_setting("llm", json.dumps(legacy))
        await m.load_saved_llm_settings()
        return (await m.llm_settings_message()).settings.model, m._settings.llm.temperature

    assert asyncio.run(run()) == ("gpt-4.1", None)
