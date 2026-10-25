import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from scribely.api import create_app
from scribely.config import Settings
from tests.test_live_session import file_capture, make_manager


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(), make_manager(file_capture(tmp_path)))) as c:
        yield c


def receive_until(ws: Any, predicate: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
    seen = []
    for _ in range(200):
        msg = json.loads(ws.receive_text())
        seen.append(msg)
        if predicate(msg):
            return seen
    raise AssertionError(f"condition not met; got {[m['type'] for m in seen]}")


def test_unknown_origin_is_refused(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers={"origin": "https://evil.example"}),
    ):
        pass


def test_record_session_over_websocket(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers={"origin": "tauri://localhost"}) as ws:
        first, second = json.loads(ws.receive_text()), json.loads(ws.receive_text())
        assert first["type"] == "status" and first["state"] == "idle"
        assert second == {"type": "transcript_snapshot", "segments": []}

        ws.send_text(json.dumps({"type": "start", "title": "Bio 101"}))
        seen = receive_until(ws, lambda m: m["type"] == "status" and m["state"] == "idle")
    finals = [m["segment"]["text"] for m in seen if m["type"] == "transcript_final"]
    assert finals == ["speech 1.0s", "speech 0.5s"]
    assert seen[-1]["session"]["title"] == "Bio 101"
    assert seen[-1]["session"]["status"] == "stopped"


def test_bad_and_invalid_commands_get_errors(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_text(), ws.receive_text()
        ws.send_text('{"type": "explode"}')
        assert json.loads(ws.receive_text())["code"] == "bad_message"
        ws.send_text('{"type": "stop"}')
        err = json.loads(ws.receive_text())
        assert err["type"] == "error" and err["code"] == "not_recording"
