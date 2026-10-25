"""Live recording sessions: capture -> streaming STT -> broadcast to WebSocket clients.

One session records at a time. Final segments of the current/last session are kept in
memory (the rolling window the live UI is fed from); SQLite is the durable copy, flushed
about once a second while recording.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

import structlog
from langchain_core.language_models import BaseChatModel

from scribely.capture import AudioCapture, CaptureError, CapturePermissionError, create_capture
from scribely.config import LLMConfig, Settings
from scribely.models import (
    BackendState,
    ErrorCode,
    ErrorMessage,
    NotesJobMessage,
    NotesMessage,
    ServerMessage,
    Session,
    SessionNotes,
    SessionOpenedMessage,
    SessionsMessage,
    SessionStatus,
    StatusMessage,
    TranscriptFinalMessage,
    TranscriptPartialMessage,
    TranscriptSegment,
    TranscriptSnapshot,
)
from scribely.pipeline import LLMError, check_llm, generate_notes, get_llm
from scribely.pipeline.llm_factory import provider_name
from scribely.session.store import SessionStore, StorageError
from scribely.stt import SileroVAD, SpeechDetector, StreamingTranscriber, STTError
from scribely.stt.transcriber import Transcriber, WhisperTranscriber

SUBSCRIBER_QUEUE_SIZE = 1000
FLUSH_INTERVAL_SECONDS = 1.0

log = structlog.get_logger(__name__)


class LoadableTranscriber(Transcriber, Protocol):
    def load(self) -> None: ...


class SessionError(Exception):
    """A request the session manager can't fulfil; ``message`` is safe to show the user."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message


class LiveSessionManager:
    def __init__(
        self,
        settings: Settings,
        *,
        store: SessionStore,
        transcriber: LoadableTranscriber | None = None,
        capture_factory: Callable[[], AudioCapture] | None = None,
        vad_factory: Callable[[], SpeechDetector] | None = None,
        llm_factory: Callable[[LLMConfig], BaseChatModel] = get_llm,
    ) -> None:
        self._settings = settings
        self._store = store
        self._transcriber: LoadableTranscriber = transcriber or WhisperTranscriber(
            settings.stt, settings.paths.resolved_models_dir()
        )
        self._capture_factory = capture_factory or (lambda: create_capture(settings.capture))
        self._vad_factory = vad_factory or (lambda: SileroVAD(settings.stt.vad_threshold))
        self._state: BackendState = "idle"
        self._session: Session | None = None
        self._segments: list[TranscriptSegment] = []
        self._subscribers: set[asyncio.Queue[ServerMessage]] = set()
        self._lock = asyncio.Lock()
        self._model_task: asyncio.Future[None] | None = None
        self._capture: AudioCapture | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._run_failed = False
        self._flush_task: asyncio.Task[None] | None = None
        self._storage_warned = False
        self._notes_jobs: dict[str, asyncio.Task[None]] = {}
        self._llm_factory = llm_factory
        self._llm_issue: str | None = None

    @property
    def state(self) -> BackendState:
        return self._state

    # --- subscriptions ----------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[ServerMessage]:
        """Register a client; its queue starts with the current status and transcript."""
        queue: asyncio.Queue[ServerMessage] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        queue.put_nowait(self._status())
        queue.put_nowait(TranscriptSnapshot(type="transcript_snapshot", segments=self._segments))
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[ServerMessage]) -> None:
        self._subscribers.discard(queue)

    def _broadcast(self, message: ServerMessage) -> None:
        for queue in self._subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("ws.client_lagging", dropped=message.type)

    def _status(self) -> StatusMessage:
        return StatusMessage(
            type="status",
            state=self._state,
            session=self._session,
            model=self._settings.stt.model,
            llm_issue=self._llm_issue,
        )

    def _set_state(self, state: BackendState) -> None:
        self._state = state
        self._broadcast(self._status())

    # --- model ------------------------------------------------------------------------------

    def warm_up(self) -> None:
        """Start loading the speech model in the background so the first Record is quick."""
        if self._model_task is None:
            self._model_task = asyncio.ensure_future(asyncio.to_thread(self._transcriber.load))
            self._model_task.add_done_callback(self._on_model_loaded)

    def _on_model_loaded(self, task: asyncio.Future[None]) -> None:
        if task.cancelled():
            return
        if (err := task.exception()) is not None:
            log.warning("stt.model_load_failed", error=str(err))
        else:
            log.info("stt.model_ready", model=self._settings.stt.model)

    async def _ensure_model(self) -> None:
        self.warm_up()
        assert self._model_task is not None
        if not self._model_task.done():
            self._set_state("loading_model")
        try:
            await asyncio.shield(self._model_task)
        except STTError as err:
            self._model_task = None  # allow a retry, e.g. after fixing the config
            raise SessionError("model_failed", str(err)) from None
        except Exception as err:
            self._model_task = None
            raise SessionError("model_failed", f"Couldn't load the speech model: {err}") from None

    # --- lifecycle --------------------------------------------------------------------------

    async def start(self, title: str | None = None) -> Session:
        async with self._lock:
            if self._state != "idle":
                raise SessionError("already_recording", "A recording is already in progress.")
            try:
                await self._ensure_model()
                capture = self._capture_factory()
                await capture.start()
            except SessionError:
                self._set_state("idle")
                raise
            except CapturePermissionError as err:
                self._set_state("idle")
                raise SessionError("capture_permission", str(err)) from None
            except CaptureError as err:
                self._set_state("idle")
                raise SessionError("capture_failed", str(err)) from None

            session = Session(
                id=uuid.uuid4().hex,
                title=title,
                status="recording",
                started_at=datetime.now(UTC),
            )
            try:
                await self._store.create_session(session)
            except StorageError as err:
                await capture.stop()
                self._set_state("idle")
                raise SessionError("storage_failed", str(err)) from None

            self._session, self._segments, self._capture = session, [], capture
            self._run_failed = self._storage_warned = False
            self._run_task = asyncio.create_task(self._run(capture, session))
            self._flush_task = asyncio.create_task(self._flush_loop())
            self._set_state("recording")
            self._broadcast(TranscriptSnapshot(type="transcript_snapshot", segments=[]))
            await self._broadcast_sessions()
            log.info("session.started", session_id=session.id)
            return session

    async def stop(self) -> Session:
        async with self._lock:
            if self._state != "recording" or self._capture is None or self._run_task is None:
                raise SessionError("not_recording", "Nothing is being recorded.")
            self._set_state("stopping")
            await self._capture.stop()
            await self._run_task  # drains the last segment; handles its own errors
            return await self._end_session("failed" if self._run_failed else "stopped")

    async def shutdown(self) -> None:
        for job in list(self._notes_jobs.values()):
            job.cancel()
        if self._state == "recording":
            await self.stop()
        elif self._run_task is not None:  # a session is finishing on its own
            await self._run_task

    async def _run(self, capture: AudioCapture, session: Session) -> None:
        stream = StreamingTranscriber(self._transcriber, self._vad_factory(), self._settings.stt)
        try:
            async for u in stream.run(capture.stream()):
                if u.final:
                    segment = TranscriptSegment(
                        session_id=session.id,
                        index=len(self._segments),
                        start=u.start,
                        end=u.end,
                        text=u.text,
                    )
                    self._segments.append(segment)
                    self._store.queue_segment(segment)
                    self._broadcast(
                        TranscriptFinalMessage(type="transcript_final", segment=segment)
                    )
                else:
                    self._broadcast(
                        TranscriptPartialMessage(
                            type="transcript_partial",
                            session_id=session.id,
                            start=u.start,
                            end=u.end,
                            text=u.text,
                        )
                    )
            if self._state == "recording":  # the source ended by itself (e.g. end of file)
                self._set_state("stopping")  # stop() now refuses; we finish the session here
                await capture.stop()
                await self._end_session("stopped")
        except Exception as err:
            self._run_failed = True
            code: ErrorCode
            if isinstance(err, CapturePermissionError):
                code, message = "capture_permission", str(err)
            elif isinstance(err, CaptureError):
                code, message = "capture_failed", str(err)
            elif isinstance(err, STTError):
                code, message = "model_failed", str(err)
            else:
                log.exception("session.failed", session_id=session.id)
                code, message = (
                    "internal",
                    f"Recording stopped because of an unexpected error: {err}",
                )
            self._broadcast(ErrorMessage(type="error", code=code, message=message))
            if self._state == "recording":  # not already being stopped by stop()
                self._set_state("stopping")
                await capture.stop()
                await self._end_session("failed")
            else:
                await capture.stop()

    async def _end_session(self, status: SessionStatus) -> Session:
        assert self._session is not None
        if self._flush_task is not None:
            self._flush_task.cancel()
            self._flush_task = None
        session = self._session.model_copy(update={"status": status, "ended_at": datetime.now(UTC)})
        self._session, self._capture, self._run_task = session, None, None
        try:
            await self._store.flush()
            await self._store.update_session(session)
        except StorageError as err:
            self._storage_error(err)
        self._set_state("idle")
        await self._broadcast_sessions()
        log.info(
            "session.ended", session_id=session.id, status=status, segments=len(self._segments)
        )
        return session

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
            try:
                await self._store.flush()
            except StorageError as err:
                self._storage_error(err)  # segments stay queued; retried next tick

    def _storage_error(self, err: StorageError) -> None:
        if not self._storage_warned:  # one banner per session, not one per second
            self._storage_warned = True
            self._broadcast(ErrorMessage(type="error", code="storage_failed", message=str(err)))

    # --- saved sessions ---------------------------------------------------------------------

    async def sessions_message(self) -> SessionsMessage:
        try:
            sessions = await self._store.list_sessions()
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        return SessionsMessage(type="sessions", sessions=sessions)

    async def _broadcast_sessions(self) -> None:
        try:
            self._broadcast(await self.sessions_message())
        except SessionError as err:
            log.warning("storage.list_failed", error=err.message)

    async def open_session(self, session_id: str) -> SessionOpenedMessage:
        if self._session is not None and self._session.id == session_id and self._state != "idle":
            # Still recording: memory is ahead of the last flush (and there are no notes yet).
            return SessionOpenedMessage(
                type="session_opened", session=self._session, segments=self._segments
            )
        try:
            found = await self._store.get_session(session_id)
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        if found is None:
            raise SessionError("not_found", "That session no longer exists.")
        session, segments = found
        try:
            notes = await self._store.get_notes(session_id)
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        return SessionOpenedMessage(
            type="session_opened", session=session, segments=segments, notes=notes
        )

    async def rename_session(self, session_id: str, title: str) -> Session:
        clean = title.strip() or None
        try:
            renamed = await self._store.rename_session(session_id, clean)
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        if renamed is None:
            raise SessionError("not_found", "That session no longer exists.")
        if self._session is not None and self._session.id == session_id:
            self._session = self._session.model_copy(update={"title": clean})
            self._broadcast(self._status())
        await self._broadcast_sessions()
        return renamed

    async def delete_session(self, session_id: str) -> None:
        is_current = self._session is not None and self._session.id == session_id
        if is_current and self._state != "idle":
            raise SessionError("session_busy", "Stop the recording before deleting it.")
        try:
            deleted = await self._store.delete_session(session_id)
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        if not deleted:
            raise SessionError("not_found", "That session no longer exists.")
        if is_current:
            self._session, self._segments = None, []
            self._broadcast(self._status())
            self._broadcast(TranscriptSnapshot(type="transcript_snapshot", segments=[]))
        await self._broadcast_sessions()

    # --- notes ------------------------------------------------------------------------------

    async def check_llm_setup(self) -> None:
        """Validate the notes LLM settings (startup and before each summarize)."""
        try:
            await check_llm(self._settings.llm)
        except LLMError as err:
            issue: str | None = str(err)
            log.warning("llm.not_ready", issue=issue)
        else:
            issue = None
        if issue != self._llm_issue:
            self._llm_issue = issue
            self._broadcast(self._status())

    async def summarize(self, session_id: str) -> None:
        """Start generating notes for a stopped session; progress and results are broadcast.

        Runs only on the user's request and never while that session is recording
        (CLAUDE.md rule 1).
        """
        if self._session is not None and self._session.id == session_id and self._state != "idle":
            raise SessionError(
                "session_busy",
                "Stop the recording first; notes are made from the finished transcript.",
            )
        if session_id in self._notes_jobs:
            raise SessionError("session_busy", "Notes for this session are already being written.")
        try:
            found = await self._store.get_session(session_id)
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        if found is None:
            raise SessionError("not_found", "That session no longer exists.")
        _, segments = found
        if not segments:
            raise SessionError(
                "llm_failed",
                "Nothing was transcribed in this session, so there's nothing to summarize.",
            )
        self._notes_jobs[session_id] = asyncio.create_task(self._summarize(session_id, segments))

    async def _summarize(self, session_id: str, segments: list[TranscriptSegment]) -> None:
        cfg = self._settings.llm

        async def progress(message: str) -> None:
            self._broadcast(
                NotesJobMessage(
                    type="notes_job", session_id=session_id, state="running", message=message
                )
            )

        try:
            await self.check_llm_setup()
            if self._llm_issue is not None:
                raise LLMError(self._llm_issue)
            await progress(f"Sending the transcript to {provider_name(cfg)} ({cfg.model})…")
            doc = await generate_notes(segments, self._llm_factory(cfg), self._settings, progress)
            notes = SessionNotes(
                session_id=session_id,
                doc=doc,
                provider=cfg.provider,
                model=cfg.model,
                created_at=datetime.now(UTC),
            )
            await self._store.save_notes(notes)
        except (LLMError, StorageError) as err:
            self._notes_failed(session_id, str(err))
        except Exception as err:
            log.exception("notes.failed", session_id=session_id)
            self._notes_failed(
                session_id, f"Couldn't write notes because of an unexpected error: {err}"
            )
        else:
            log.info("notes.done", session_id=session_id, sections=len(doc.sections))
            self._broadcast(
                NotesJobMessage(
                    type="notes_job", session_id=session_id, state="done", message="Notes ready."
                )
            )
            self._broadcast(NotesMessage(type="notes", notes=notes))
            await self._broadcast_sessions()
        finally:
            self._notes_jobs.pop(session_id, None)

    def _notes_failed(self, session_id: str, message: str) -> None:
        log.warning("notes.failed", session_id=session_id, error=message)
        self._broadcast(
            NotesJobMessage(
                type="notes_job", session_id=session_id, state="failed", message=message
            )
        )
        self._broadcast(ErrorMessage(type="error", code="llm_failed", message=message))
