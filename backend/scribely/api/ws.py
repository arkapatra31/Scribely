"""``/ws``: the single WebSocket the desktop UI talks to."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from scribely.models import (
    ClientMessage,
    DeleteSessionCommand,
    ErrorMessage,
    ListSessionsCommand,
    OpenSessionCommand,
    RenameSessionCommand,
    ServerMessage,
    StartCommand,
    StopCommand,
    SummarizeCommand,
)
from scribely.session import LiveSessionManager, SessionError

_client_messages: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def register_ws(app: FastAPI, manager: LiveSessionManager, allowed_origins: list[str]) -> None:
    allowed = set(allowed_origins)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        # Browsers always send Origin; refusing unknown ones stops arbitrary websites from
        # driving the local backend (cross-site WebSocket hijacking). Non-browser local
        # clients send none.
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in allowed:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        queue = manager.subscribe()
        sender = asyncio.create_task(_send_loop(websocket, queue))
        await _handle(ListSessionsCommand(type="list_sessions"), manager, queue)
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    command = _client_messages.validate_json(raw)
                except ValidationError:
                    queue.put_nowait(
                        ErrorMessage(
                            type="error", code="bad_message", message="Unrecognised command."
                        )
                    )
                    continue
                await _handle(command, manager, queue)
        except WebSocketDisconnect:
            pass
        finally:
            manager.unsubscribe(queue)
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender


async def _handle(
    command: ClientMessage, manager: LiveSessionManager, queue: asyncio.Queue[ServerMessage]
) -> None:
    """Run one command; replies and errors go to this client only, changes are broadcast."""
    try:
        match command:
            case StartCommand():
                await manager.start(command.title)
            case StopCommand():
                await manager.stop()
            case ListSessionsCommand():
                queue.put_nowait(await manager.sessions_message())
            case OpenSessionCommand():
                queue.put_nowait(await manager.open_session(command.session_id))
            case RenameSessionCommand():
                await manager.rename_session(command.session_id, command.title)
            case DeleteSessionCommand():
                await manager.delete_session(command.session_id)
            case SummarizeCommand():
                await manager.summarize(command.session_id)
    except SessionError as err:
        queue.put_nowait(ErrorMessage(type="error", code=err.code, message=err.message))


async def _send_loop(websocket: WebSocket, queue: asyncio.Queue[ServerMessage]) -> None:
    while True:
        message = await queue.get()
        await websocket.send_text(message.model_dump_json())
