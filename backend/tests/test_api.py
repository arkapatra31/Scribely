from fastapi.testclient import TestClient

from scribely import __version__
from scribely.api import create_app
from scribely.config import Settings


def test_health() -> None:
    client = TestClient(create_app(Settings()))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}
