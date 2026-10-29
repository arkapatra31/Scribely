import asyncio
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import BaseModel

from scribely.capture.base import AudioCapture, CaptureError, CapturePermissionError
from scribely.capture.dsp import TARGET_SAMPLE_RATE as SR
from scribely.capture.file import FileCapture
from scribely.config import LLMConfig, Settings, SttConfig
from scribely.credentials import Credentials
from scribely.models import (
    ErrorMessage,
    ServerMessage,
    Session,
    StatusMessage,
    TranscriptFinalMessage,
)
from scribely.pipeline.schemas import DraftNotes, DraftSection
from scribely.session import LiveSessionManager, SessionError
from scribely.session.store import SessionStore, StorageError
from scribely.stt import STTError
from tests.audio import write_wav
from tests.fake_llm import FakeLLM
from tests.stt_fakes import EnergyVAD, LoadableFakeTranscriber, quiet, tone

LECTURE = np.concatenate([quiet(0.3), tone(1.0), quiet(1.0), tone(0.5), quiet(0.8)])


def make_manager(
    capture_factory: Callable[[], AudioCapture],
    transcriber: LoadableFakeTranscriber | None = None,
    store: SessionStore | None = None,
    llm: FakeLLM | None = None,
) -> LiveSessionManager:
    fake_llm = llm or FakeLLM(notes_handler)
    return LiveSessionManager(
        Settings(
            stt=SttConfig(partial_interval_seconds=0),
            llm=LLMConfig(azure_endpoint="https://example.openai.azure.com/"),
        ),
        store=store or SessionStore.open(Path(tempfile.mkdtemp()) / "scribely.db"),
        transcriber=transcriber or LoadableFakeTranscriber(),
        capture_factory=capture_factory,
        vad_factory=EnergyVAD,
        llm_factory=lambda cfg, key: fake_llm.as_chat_model(),
        credentials=Credentials(),
    )


def notes_handler(schema: type[BaseModel], prompt: str) -> BaseModel:
    return DraftNotes(
        title="Lecture notes",
        summary="What was said.",
        sections=[DraftSection(heading="Intro", points=["speech"], start_seconds=0, end_seconds=2)],
    )


def file_capture(
    tmp_path: Path, audio: Any = LECTURE, realtime: bool = False
) -> Callable[[], AudioCapture]:
    path = write_wav(tmp_path / "lecture.wav", audio, SR)
    return lambda: FileCapture(path, realtime=realtime)


def drain(queue: asyncio.Queue[ServerMessage]) -> list[ServerMessage]:
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


async def wait_idle(manager: LiveSessionManager, timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while manager.state != "idle":
            await asyncio.sleep(0.01)


class FailingCapture(AudioCapture):
    """Delivers a second of speech, then reports a device failure."""

    name = "failing"

    async def _open(self) -> None:
        def run() -> None:
            self._push(tone(1.0), SR)
            self._fail(CaptureError("Your output device was disconnected."))

        threading.Thread(target=run, daemon=True).start()

    async def _close(self) -> None:
        pass


class DeniedCapture(AudioCapture):
    name = "denied"

    async def _open(self) -> None:
        raise CapturePermissionError("Grant Screen & System Audio Recording permission.")

    async def _close(self) -> None:
        pass


def test_session_streams_segments_and_ends_with_source(tmp_path: Path) -> None:
    async def run() -> list[ServerMessage]:
        manager = make_manager(file_capture(tmp_path))
        queue = manager.subscribe()
        session = await manager.start("Lecture 1")
        assert session.status == "recording" and session.title == "Lecture 1"
        await wait_idle(manager)
        return drain(queue)

    messages = asyncio.run(run())
    finals = [m for m in messages if isinstance(m, TranscriptFinalMessage)]
    assert [f.segment.text for f in finals] == ["speech 1.0s", "speech 0.5s"]
    assert [f.segment.index for f in finals] == [0, 1]
    states = [m.state for m in messages if isinstance(m, StatusMessage)]
    assert states[0] == "idle" and "recording" in states and states[-1] == "idle"
    last = [m for m in messages if isinstance(m, StatusMessage)][-1]
    assert last.session is not None and last.session.status == "stopped"
    assert last.session.ended_at is not None


def test_stop_drains_and_marks_stopped(tmp_path: Path) -> None:
    async def run() -> tuple[str, list[ServerMessage]]:
        manager = make_manager(
            file_capture(tmp_path, np.concatenate([tone(0.6), quiet(30)]), realtime=True)
        )
        queue = manager.subscribe()
        await manager.start()
        await asyncio.sleep(1.5)
        session = await manager.stop()
        return session.status, drain(queue)

    status, messages = asyncio.run(run())
    assert status == "stopped"
    assert any(isinstance(m, TranscriptFinalMessage) for m in messages)


def test_double_start_and_idle_stop_are_rejected(tmp_path: Path) -> None:
    async def run() -> None:
        manager = make_manager(file_capture(tmp_path, quiet(30), realtime=True))
        with pytest.raises(SessionError) as exc:
            await manager.stop()
        assert exc.value.code == "not_recording"
        await manager.start()
        with pytest.raises(SessionError) as exc:
            await manager.start()
        assert exc.value.code == "already_recording"
        await manager.stop()

    asyncio.run(run())


def test_model_failure_is_reported_and_retryable(tmp_path: Path) -> None:
    transcriber = LoadableFakeTranscriber(load_error=STTError('Unknown speech model "x".'))

    async def run() -> None:
        manager = make_manager(file_capture(tmp_path), transcriber)
        with pytest.raises(SessionError) as exc:
            await manager.start()
        assert exc.value.code == "model_failed"
        assert "Unknown speech model" in exc.value.message
        assert manager.state == "idle"
        transcriber.load_error = None
        await manager.start()
        await wait_idle(manager)

    asyncio.run(run())
    assert transcriber.loads == 2


def test_permission_denied_at_start(tmp_path: Path) -> None:
    async def run() -> None:
        manager = make_manager(DeniedCapture)
        with pytest.raises(SessionError) as exc:
            await manager.start()
        assert exc.value.code == "capture_permission"
        assert manager.state == "idle"

    asyncio.run(run())


def test_capture_failure_mid_session_fails_session(tmp_path: Path) -> None:
    async def run() -> list[ServerMessage]:
        manager = make_manager(FailingCapture)
        queue = manager.subscribe()
        await manager.start()
        await wait_idle(manager)
        return drain(queue)

    messages = asyncio.run(run())
    errors = [m for m in messages if isinstance(m, ErrorMessage)]
    assert errors and errors[0].code == "capture_failed"
    assert "disconnected" in errors[0].message
    last = [m for m in messages if isinstance(m, StatusMessage)][-1]
    assert last.state == "idle" and last.session is not None and last.session.status == "failed"


def test_new_subscriber_gets_last_session_snapshot(tmp_path: Path) -> None:
    async def run() -> list[ServerMessage]:
        manager = make_manager(file_capture(tmp_path))
        await manager.start()
        await wait_idle(manager)
        return drain(manager.subscribe())

    status, snapshot, model = asyncio.run(run())
    assert isinstance(status, StatusMessage) and status.session is not None
    assert snapshot.type == "transcript_snapshot"
    assert model.type == "speech_model" and model.state == "ready"
    assert [s.text for s in snapshot.segments] == ["speech 1.0s", "speech 0.5s"]


def test_segments_are_persisted_and_survive_restart(tmp_path: Path) -> None:
    db = tmp_path / "scribely.db"

    async def run() -> str:
        manager = make_manager(file_capture(tmp_path), store=SessionStore.open(db))
        session = await manager.start("Persisted")
        await wait_idle(manager)
        return session.id

    session_id = asyncio.run(run())
    reopened = SessionStore.open(db)
    found = asyncio.run(reopened.get_session(session_id))
    assert found is not None
    session, segments = found
    assert session.status == "stopped" and session.title == "Persisted"
    assert [s.text for s in segments] == ["speech 1.0s", "speech 0.5s"]


def test_live_session_can_be_opened_and_not_deleted_while_recording(tmp_path: Path) -> None:
    async def run() -> None:
        manager = make_manager(
            file_capture(tmp_path, np.concatenate([tone(0.6), quiet(30)]), realtime=True)
        )
        session = await manager.start()
        await asyncio.sleep(1.5)
        opened = await manager.open_session(session.id)
        assert opened.session.status == "recording"
        assert len(opened.segments) == 1
        with pytest.raises(SessionError) as exc:
            await manager.delete_session(session.id)
        assert exc.value.code == "session_busy"
        await manager.stop()
        await manager.delete_session(session.id)
        assert (await manager.sessions_message()).sessions == []

    asyncio.run(run())


def test_storage_failure_at_start_is_reported(tmp_path: Path) -> None:
    class FullDiskStore(SessionStore):
        async def create_session(self, session: Session) -> None:
            raise StorageError("Couldn't save or load sessions: database or disk is full.")

    store = FullDiskStore.open(tmp_path / "scribely.db")

    async def run() -> None:
        manager = make_manager(file_capture(tmp_path), store=store)
        with pytest.raises(SessionError) as exc:
            await manager.start()
        assert exc.value.code == "storage_failed"
        assert "disk is full" in exc.value.message
        assert manager.state == "idle"

    asyncio.run(run())


async def wait_notes(
    queue: asyncio.Queue[ServerMessage], timeout: float = 5.0
) -> list[ServerMessage]:
    seen: list[ServerMessage] = []
    async with asyncio.timeout(timeout):
        while True:
            message = await queue.get()
            seen.append(message)
            if message.type == "notes_job" and message.state in ("done", "failed"):
                await asyncio.sleep(0.05)  # let the trailing notes/sessions broadcasts land
                seen.extend(drain(queue))
                return seen


def test_summarize_on_demand_saves_and_broadcasts_notes(tmp_path: Path) -> None:
    async def run() -> tuple[list[ServerMessage], Any]:
        manager = make_manager(file_capture(tmp_path))
        session = await manager.start()
        await wait_idle(manager)
        queue = manager.subscribe()
        drain(queue)
        await manager.summarize(session.id)
        messages = await wait_notes(queue)
        opened = await manager.open_session(session.id)
        return messages, opened

    messages, opened = asyncio.run(run())
    jobs = [m for m in messages if m.type == "notes_job"]
    assert jobs[0].state == "running" and "Azure OpenAI" in jobs[0].message
    assert jobs[-1].state == "done"
    notes = [m for m in messages if m.type == "notes"]
    assert notes and notes[0].notes.doc.title == "Lecture notes"
    listing = [m for m in messages if m.type == "sessions"][-1]
    assert listing.sessions[0].has_notes is True
    assert opened.notes is not None and opened.notes.model == "gpt-4o"


def test_summarize_is_refused_while_recording_and_for_empty_sessions(tmp_path: Path) -> None:
    async def run() -> None:
        manager = make_manager(
            file_capture(tmp_path, np.concatenate([tone(0.6), quiet(30)]), realtime=True)
        )
        session = await manager.start()
        with pytest.raises(SessionError) as exc:
            await manager.summarize(session.id)
        assert exc.value.code == "session_busy"
        await manager.stop()

        silent = make_manager(file_capture(tmp_path, quiet(2)))
        empty = await silent.start()
        await wait_idle(silent)
        with pytest.raises(SessionError) as exc:
            await silent.summarize(empty.id)
        assert exc.value.code == "llm_failed" and "Nothing was transcribed" in exc.value.message
        with pytest.raises(SessionError) as exc:
            await silent.summarize("missing")
        assert exc.value.code == "not_found"

    asyncio.run(run())


def test_llm_failure_is_reported(tmp_path: Path) -> None:
    class AuthenticationError(Exception):
        status_code = 401

    def boom(schema: type[BaseModel], prompt: str) -> BaseModel:
        raise AuthenticationError("bad key")

    async def run() -> list[ServerMessage]:
        manager = make_manager(file_capture(tmp_path), llm=FakeLLM(boom))
        session = await manager.start()
        await wait_idle(manager)
        queue = manager.subscribe()
        drain(queue)
        await manager.summarize(session.id)
        return await wait_notes(queue)

    messages = asyncio.run(run())
    failed = [m for m in messages if m.type == "notes_job"][-1]
    assert failed.state == "failed" and "rejected the API key" in failed.message
    assert any(m.type == "error" and m.code == "llm_failed" for m in messages)


def test_llm_setup_issue_is_reported_in_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    async def run() -> tuple[str | None, list[ServerMessage]]:
        manager = make_manager(file_capture(tmp_path))
        session = await manager.start()
        await wait_idle(manager)
        queue = manager.subscribe()
        drain(queue)
        await manager.check_llm_setup()
        status = manager._status().llm_issue
        await manager.summarize(session.id)
        return status, await wait_notes(queue)

    issue, messages = asyncio.run(run())
    assert issue is not None and "AZURE_OPENAI_API_KEY" in issue
    assert [m for m in messages if m.type == "notes_job"][-1].state == "failed"
