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
        first, second, third = (json.loads(ws.receive_text()) for _ in range(3))
        assert first["type"] == "status" and first["state"] == "idle"
        assert second == {"type": "transcript_snapshot", "segments": []}
        assert third == {"type": "sessions", "sessions": []}

        ws.send_text(json.dumps({"type": "start", "title": "Bio 101"}))
        seen = receive_until(ws, lambda m: m["type"] == "status" and m["state"] == "idle")
    finals = [m["segment"]["text"] for m in seen if m["type"] == "transcript_final"]
    assert finals == ["speech 1.0s", "speech 0.5s"]
    assert seen[-1]["session"]["title"] == "Bio 101"
    assert seen[-1]["session"]["status"] == "stopped"


def test_bad_and_invalid_commands_get_errors(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        for _ in range(3):
            ws.receive_text()
        ws.send_text('{"type": "explode"}')
        assert json.loads(ws.receive_text())["code"] == "bad_message"
        ws.send_text('{"type": "stop"}')
        err = json.loads(ws.receive_text())
        assert err["type"] == "error" and err["code"] == "not_recording"


def test_saved_sessions_over_websocket(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        for _ in range(3):
            ws.receive_text()
        ws.send_text(json.dumps({"type": "start"}))
        seen = receive_until(ws, lambda m: m["type"] == "status" and m["state"] == "idle")
        session_id = seen[-1]["session"]["id"]
        listing = receive_until(ws, lambda m: m["type"] == "sessions")[-1]
        assert listing["sessions"][0]["session"]["id"] == session_id
        assert listing["sessions"][0]["segment_count"] == 2

        ws.send_text(
            json.dumps({"type": "rename_session", "session_id": session_id, "title": " Bio "})
        )
        renamed = receive_until(ws, lambda m: m["type"] == "sessions")[-1]
        assert renamed["sessions"][0]["session"]["title"] == "Bio"

        ws.send_text(json.dumps({"type": "open_session", "session_id": session_id}))
        opened = receive_until(ws, lambda m: m["type"] == "session_opened")[-1]
        assert [s["text"] for s in opened["segments"]] == ["speech 1.0s", "speech 0.5s"]

        ws.send_text(json.dumps({"type": "delete_session", "session_id": session_id}))
        after = receive_until(ws, lambda m: m["type"] == "sessions")[-1]
        assert after["sessions"] == []

        ws.send_text(json.dumps({"type": "open_session", "session_id": session_id}))
        err = receive_until(ws, lambda m: m["type"] == "error")[-1]
        assert err["code"] == "not_found"


def test_new_commands_reply_to_the_sender(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        for _ in range(3):
            ws.receive_text()
        replies = {}
        for command in (
            {"type": "pause"},
            {"type": "search_sessions", "query": "cells"},
            {"type": "get_speech_settings"},
            {"type": "capture_permission", "action": "check"},
            {"type": "get_diagnostics"},
        ):
            ws.send_text(json.dumps(command))
            reply = json.loads(ws.receive_text())
            replies[command["type"]] = reply
    assert replies["pause"]["code"] == "not_recording"
    assert replies["search_sessions"] == {"type": "search_results", "query": "cells", "hits": []}
    assert replies["get_speech_settings"]["settings"]["model"] == "small"
    assert replies["capture_permission"]["type"] == "capture_permission"
    assert replies["get_diagnostics"]["text"].startswith("Scribely ")


def test_unknown_language_is_a_bad_message(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        for _ in range(3):
            ws.receive_text()
        ws.send_text(
            json.dumps(
                {"type": "save_speech_settings", "settings": {"model": "small", "language": "zz"}}
            )
        )
        reply = json.loads(ws.receive_text())
    assert reply["code"] == "bad_message" and "Unknown language" in reply["message"]
