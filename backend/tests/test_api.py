from pathlib import Path

from fastapi.testclient import TestClient

from scribely import __version__
from scribely.api import create_app
from scribely.config import Settings
from scribely.session import LiveSessionManager
from scribely.session.store import SessionStore


def test_health(tmp_path: Path) -> None:
    store = SessionStore.open(tmp_path / "scribely.db")
    client = TestClient(create_app(Settings(), LiveSessionManager(Settings(), store=store)))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}
