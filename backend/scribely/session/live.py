"""Live recording sessions: capture -> streaming STT -> broadcast to WebSocket clients.

One session records at a time. Final segments of the current/last session are kept in
memory (the rolling window the live UI is fed from); SQLite is the durable copy, flushed
about once a second while recording.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import platform
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import numpy as np
import structlog
from langchain_core.language_models import BaseChatModel

from scribely import __version__
from scribely import log as logfile
from scribely.capture import (
    AudioCapture,
    AudioChunk,
    CaptureError,
    CapturePermissionError,
    create_capture,
)
from scribely.capture import permission as capture_permission
from scribely.config import LLMConfig, Settings, SttConfig
from scribely.credentials import Credentials
from scribely.export import (
    PdfUnavailableError,
    export_filename,
    render_session_html,
    render_session_pdf,
)
from scribely.models import (
    AudioLevelMessage,
    BackendState,
    CapturePermissionMessage,
    DiagnosticsMessage,
    ErrorCode,
    ErrorMessage,
    ExportedMessage,
    ExportFormat,
    LanguageOption,
    LlmSettings,
    LlmSettingsMessage,
    LlmTestMessage,
    NoteDoc,
    NotesJobMessage,
    NotesMessage,
    NotesStyle,
    RestructureStyle,
    SearchResultsMessage,
    ServerMessage,
    Session,
    SessionNotes,
    SessionOpenedMessage,
    SessionsMessage,
    SessionStatus,
    SpeechModelMessage,
    SpeechModelOption,
    SpeechSettings,
    SpeechSettingsMessage,
    StatusMessage,
    TranscriptFinalMessage,
    TranscriptPartialMessage,
    TranscriptSegment,
    TranscriptSnapshot,
)
from scribely.pipeline import LLMError, check_llm, generate_notes, get_llm
from scribely.pipeline.graph import Progress
from scribely.pipeline.llm_factory import (
    SUGGESTED_MODELS,
    explain_error,
    list_ollama_models,
    provider_name,
)
from scribely.pipeline.restructure import restructure_notes
from scribely.session.store import SessionStore, StorageError
from scribely.stt import SileroVAD, SpeechDetector, StreamingTranscriber, STTError, catalog
from scribely.stt.transcriber import LoadProgress, ModelPhase, Transcriber, WhisperTranscriber

SUBSCRIBER_QUEUE_SIZE = 1000
LLM_SETTINGS_KEY = "llm"
STT_SETTINGS_KEY = "stt"
ONBOARDED_KEY = "onboarded"
FLUSH_INTERVAL_SECONDS = 1.0
LEVEL_INTERVAL_SECONDS = 0.1
LEVEL_FLOOR_DB = -60.0

log = structlog.get_logger(__name__)


class LoadableTranscriber(Transcriber, Protocol):
    def load(self, on_progress: LoadProgress | None = None) -> None: ...

    def configure(self, cfg: SttConfig) -> None: ...


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
        llm_factory: Callable[[LLMConfig, str | None], BaseChatModel] = get_llm,
        credentials: Credentials | None = None,
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
        self._credentials = credentials or Credentials()
        self._llm_issue: str | None = None
        self._speech_model: SpeechModelMessage | None = None
        self._onboarded = True
        # Recorded time excluding pauses: seconds before the last resume + the running stretch.
        self._recorded_before = 0.0
        self._recording_since: float | None = None

    @property
    def state(self) -> BackendState:
        return self._state

    # --- subscriptions ----------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[ServerMessage]:
        """Register a client; its queue starts with the current status and transcript."""
        queue: asyncio.Queue[ServerMessage] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        queue.put_nowait(self._status())
        queue.put_nowait(TranscriptSnapshot(type="transcript_snapshot", segments=self._segments))
        if self._speech_model is not None:
            queue.put_nowait(self._speech_model)
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
            elapsed=self._elapsed(),
            onboarded=self._onboarded,
        )

    def _elapsed(self) -> float:
        running = time.monotonic() - self._recording_since if self._recording_since else 0.0
        return self._recorded_before + running

    def _set_state(self, state: BackendState) -> None:
        self._state = state
        self._broadcast(self._status())

    # --- model ------------------------------------------------------------------------------

    async def startup(self) -> None:
        """Apply saved settings, then get the speech model ready unless first-run setup is
        still to pick one."""
        await self.load_saved_llm_settings()
        await self.load_saved_speech_settings()
        try:
            onboarded = await self._store.get_setting(ONBOARDED_KEY) == "1"
            # People who recorded before onboarding existed don't need it.
            self._onboarded = onboarded or bool(await self._store.list_sessions())
        except StorageError as err:
            log.warning("settings.load_failed", error=str(err))
        model = self._settings.stt.model
        downloaded = await asyncio.to_thread(
            catalog.is_downloaded, model, self._settings.paths.resolved_models_dir()
        )
        if self._onboarded or downloaded:
            self.warm_up()

    def warm_up(self) -> None:
        """Start downloading/loading the speech model in the background so Record is quick."""
        if self._model_task is None:
            loop = asyncio.get_running_loop()
            model = self._settings.stt.model

            def progress(phase: ModelPhase, fraction: float | None) -> None:
                loop.call_soon_threadsafe(self._model_progress, model, phase, fraction)

            self._model_task = asyncio.ensure_future(
                asyncio.to_thread(self._transcriber.load, progress)
            )
            self._model_task.add_done_callback(lambda t: self._on_model_loaded(t, model))

    def _model_progress(self, model: str, phase: ModelPhase, fraction: float | None) -> None:
        if model != self._settings.stt.model:
            return
        label = _model_label(model)
        message = (
            f"Downloading the {label} speech model…"
            if phase == "downloading"
            else f"Loading the {label} speech model…"
        )
        self._set_speech_model(
            SpeechModelMessage(
                type="speech_model", model=model, state=phase, progress=fraction, message=message
            )
        )

    def _on_model_loaded(self, task: asyncio.Future[None], model: str) -> None:
        if task.cancelled():
            return
        if (err := task.exception()) is not None:
            log.warning("stt.model_load_failed", model=model, error=str(err))
            if self._model_task is task:
                self._model_task = None  # the next warm_up() or Record retries
            state, message = "failed", str(err)
        else:
            log.info("stt.model_ready", model=model)
            state, message = "ready", f"The {_model_label(model)} speech model is ready."
        if model == self._settings.stt.model:
            self._set_speech_model(
                SpeechModelMessage(type="speech_model", model=model, state=state, message=message)
            )

    def _set_speech_model(self, message: SpeechModelMessage) -> None:
        self._speech_model = message
        self._broadcast(message)

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
            self._recorded_before, self._recording_since = 0.0, time.monotonic()
            self._run_task = asyncio.create_task(self._run(capture, session))
            self._flush_task = asyncio.create_task(self._flush_loop())
            self._set_state("recording")
            self._broadcast(TranscriptSnapshot(type="transcript_snapshot", segments=[]))
            await self._broadcast_sessions()
            log.info("session.started", session_id=session.id)
            return session

    async def stop(self) -> Session:
        async with self._lock:
            if (
                self._state not in ("recording", "paused")
                or self._capture is None
                or self._run_task is None
            ):
                raise SessionError("not_recording", "Nothing is being recorded.")
            self._set_state("stopping")
            await self._capture.stop()
            await self._run_task  # drains the last segment; handles its own errors
            return await self._end_session("failed" if self._run_failed else "stopped")

    async def pause(self) -> None:
        """Stop listening without ending the session; the timer and timestamps pause too."""
        async with self._lock:
            if self._state != "recording" or self._capture is None:
                raise SessionError("not_recording", "Nothing is being recorded.")
            self._capture.pause()
            self._recorded_before = self._elapsed()
            self._recording_since = None
            self._broadcast(AudioLevelMessage(type="audio_level", level=0.0))
            self._set_state("paused")
            log.info("session.paused", session_id=self._session.id if self._session else None)

    async def resume(self) -> None:
        async with self._lock:
            if self._state != "paused" or self._capture is None:
                raise SessionError("not_recording", "The recording isn't paused.")
            self._capture.resume()
            self._recording_since = time.monotonic()
            self._set_state("recording")
            log.info("session.resumed", session_id=self._session.id if self._session else None)

    async def shutdown(self) -> None:
        for job in list(self._notes_jobs.values()):
            job.cancel()
        if self._state in ("recording", "paused"):
            await self.stop()
        elif self._run_task is not None:  # a session is finishing on its own
            await self._run_task

    async def _run(self, capture: AudioCapture, session: Session) -> None:
        stream = StreamingTranscriber(self._transcriber, self._vad_factory(), self._settings.stt)
        try:
            async for u in stream.run(self._metered(capture.stream())):
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
            if self._state in ("recording", "paused"):  # the source ended by itself (e.g. EOF)
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
            if self._state in ("recording", "paused"):  # not already being stopped by stop()
                self._set_state("stopping")
                await capture.stop()
                await self._end_session("failed")
            else:
                await capture.stop()

    async def _metered(self, chunks: AsyncIterator[AudioChunk]) -> AsyncIterator[AudioChunk]:
        """Pass chunks through, broadcasting the loudest level about 10 times a second."""
        peak, last = 0.0, 0.0
        async for chunk in chunks:
            if len(chunk.samples):
                rms = float(np.sqrt(np.mean(np.square(chunk.samples, dtype=np.float64))))
                peak = max(peak, rms)
                now = time.monotonic()
                if now - last >= LEVEL_INTERVAL_SECONDS:
                    self._broadcast(AudioLevelMessage(type="audio_level", level=_level(peak)))
                    peak, last = 0.0, now
            yield chunk

    async def _end_session(self, status: SessionStatus) -> Session:
        assert self._session is not None
        self._recorded_before, self._recording_since = self._elapsed(), None
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

    async def search(self, query: str) -> SearchResultsMessage:
        try:
            hits = await self._store.search(query)
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        return SearchResultsMessage(type="search_results", query=query, hits=hits)

    # --- notes ------------------------------------------------------------------------------

    async def check_llm_setup(self) -> None:
        """Validate the notes LLM settings (startup and before each summarize)."""
        try:
            cfg = self._settings.llm
            await check_llm(cfg, self._credentials.get(cfg.provider))
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
        cfg = self._settings.llm

        async def produce(progress: Progress) -> NoteDoc:
            await progress(f"Sending the transcript to {provider_name(cfg)} ({cfg.model})…")
            llm = self._llm_factory(cfg, self._credentials.get(cfg.provider))
            return await generate_notes(segments, llm, self._settings, progress)

        self._start_notes_job(session_id, produce, style="standard")

    async def restructure(self, session_id: str, style: RestructureStyle) -> None:
        """Rewrite a session's current notes (including hand edits) in another style."""
        self._check_can_write_notes(session_id)
        notes = await self._get_notes(session_id)
        if notes is None:
            raise SessionError("not_found", "Summarize this session first, then restructure it.")
        cfg = self._settings.llm

        async def produce(progress: Progress) -> NoteDoc:
            await progress(f"Restructuring with {provider_name(cfg)} ({cfg.model})…")
            llm = self._llm_factory(cfg, self._credentials.get(cfg.provider))
            return await restructure_notes(notes.doc, style, llm, self._settings)

        self._start_notes_job(session_id, produce, style=style)

    def _check_can_write_notes(self, session_id: str) -> None:
        if self._session is not None and self._session.id == session_id and self._state != "idle":
            raise SessionError(
                "session_busy",
                "Stop the recording first; notes are made from the finished transcript.",
            )
        if session_id in self._notes_jobs:
            raise SessionError("session_busy", "Notes for this session are already being written.")

    async def _get_notes(self, session_id: str) -> SessionNotes | None:
        try:
            return await self._store.get_notes(session_id)
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None

    def _start_notes_job(
        self,
        session_id: str,
        produce: Callable[[Progress], Awaitable[NoteDoc]],
        style: NotesStyle,
    ) -> None:
        self._notes_jobs[session_id] = asyncio.create_task(
            self._notes_job(session_id, produce, style)
        )

    async def _notes_job(
        self,
        session_id: str,
        produce: Callable[[Progress], Awaitable[NoteDoc]],
        style: NotesStyle,
    ) -> None:
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
            doc = await produce(progress)
            notes = SessionNotes(
                session_id=session_id,
                doc=doc,
                provider=cfg.provider,
                model=cfg.model,
                created_at=datetime.now(UTC),
                style=style,
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
            log.info("notes.done", session_id=session_id, style=style, sections=len(doc.sections))
            self._broadcast(
                NotesJobMessage(
                    type="notes_job", session_id=session_id, state="done", message="Notes ready."
                )
            )
            self._broadcast(NotesMessage(type="notes", notes=notes))
            await self._broadcast_sessions()
        finally:
            self._notes_jobs.pop(session_id, None)

    async def update_notes(self, session_id: str, doc: NoteDoc) -> SessionNotes:
        """Save notes edited by hand."""
        if session_id in self._notes_jobs:
            raise SessionError("session_busy", "Wait until the notes finish generating.")
        notes = await self._get_notes(session_id)
        if notes is None:
            raise SessionError("not_found", "This session has no notes to edit.")
        edited = notes.model_copy(update={"doc": doc, "edited": True})
        try:
            await self._store.save_notes(edited)
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        self._broadcast(NotesMessage(type="notes", notes=edited))
        return edited

    # --- export -------------------------------------------------------------------------------

    async def export_session(self, session_id: str, fmt: ExportFormat = "html") -> ExportedMessage:
        """Write notes (if any) and the full transcript as one standalone HTML or PDF file."""
        try:
            found = await self._store.get_session(session_id)
            notes = await self._store.get_notes(session_id) if found else None
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        if found is None:
            raise SessionError("not_found", "That session no longer exists.")
        session, segments = found
        if self._session is not None and self._session.id == session_id and self._state != "idle":
            segments = self._segments  # still recording: memory is ahead of the last flush
        if not segments and notes is None:
            raise SessionError(
                "export_failed", "This session is empty, so there's nothing to export."
            )

        directory = self._settings.paths.resolved_exports_dir()

        def write() -> Path:
            directory.mkdir(parents=True, exist_ok=True)
            if fmt == "pdf":
                pdf = render_session_pdf(session, segments, notes)
                path = export_filename(session, notes, directory, ".pdf")
                path.write_bytes(pdf)
            else:
                path = export_filename(session, notes, directory)
                path.write_text(render_session_html(session, segments, notes), encoding="utf-8")
            return path

        try:
            path = await asyncio.to_thread(write)
        except PdfUnavailableError as err:
            raise SessionError("export_failed", str(err)) from None
        except OSError as err:
            raise SessionError(
                "export_failed", f"Couldn't write the export to {directory}: {err.strerror or err}."
            ) from None
        log.info("export.done", session_id=session_id, format=fmt, path=str(path))
        return ExportedMessage(
            type="exported", session_id=session_id, path=str(path), filename=path.name
        )

    async def reveal_export(self, path: str) -> None:
        """Show an exported file in Finder / Explorer. Only files in the exports folder."""
        exports = self._settings.paths.resolved_exports_dir().resolve()
        target = Path(path).resolve()
        if not target.is_relative_to(exports) or not target.is_file():
            raise SessionError("export_failed", "That export no longer exists.")
        if sys.platform == "darwin":
            command = ["open", "-R", str(target)]
        elif sys.platform == "win32":
            command = ["explorer", f"/select,{target}"]
        else:
            command = ["xdg-open", str(target.parent)]
        try:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as err:
            raise SessionError("export_failed", f"Couldn't open the folder: {err}.") from None

    def _notes_failed(self, session_id: str, message: str) -> None:
        log.warning("notes.failed", session_id=session_id, error=message)
        self._broadcast(
            NotesJobMessage(
                type="notes_job", session_id=session_id, state="failed", message=message
            )
        )
        self._broadcast(ErrorMessage(type="error", code="llm_failed", message=message))

    # --- LLM settings (Settings panel) ------------------------------------------------------

    async def load_saved_llm_settings(self) -> None:
        """Apply LLM settings saved from the Settings panel; they override config.toml."""
        try:
            raw = await self._store.get_setting(LLM_SETTINGS_KEY)
        except StorageError as err:
            log.warning("settings.load_failed", error=str(err))
            return
        if raw is None:
            return
        try:
            data = json.loads(raw)
            data.pop("temperature", None)  # saved by older versions; no longer a setting
            saved = LlmSettings.model_validate(data)
        except ValueError:
            log.warning("settings.invalid_saved_llm_settings")
            return
        self._apply_llm_settings(saved)

    def _apply_llm_settings(self, saved: LlmSettings) -> None:
        llm = self._settings.llm.model_copy(update=saved.model_dump())
        self._settings = self._settings.model_copy(update={"llm": llm})

    def _current_llm_settings(self) -> LlmSettings:
        cfg = self._settings.llm
        return LlmSettings.model_validate(
            cfg.model_dump(include=set(LlmSettings.model_fields)), strict=False
        )

    async def llm_settings_message(self) -> LlmSettingsMessage:
        ollama_models: list[str] = []
        if self._settings.llm.provider == "ollama":
            with contextlib.suppress(LLMError):  # status.llm_issue explains it
                host = self._settings.llm.ollama_host
                ollama_models = await list_ollama_models(host, timeout=2.0)
        return LlmSettingsMessage(
            type="llm_settings",
            settings=self._current_llm_settings(),
            key_sources={p: self._credentials.source(p) for p in SUGGESTED_MODELS},  # type: ignore[arg-type]
            suggested_models=SUGGESTED_MODELS,
            ollama_models=ollama_models,
        )

    async def save_llm_settings(self, settings: LlmSettings, api_key: str | None) -> None:
        try:
            # Only the non-secret settings are saved; the key stays in memory.
            await self._store.set_setting(LLM_SETTINGS_KEY, settings.model_dump_json())
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        if api_key is not None:
            if api_key.strip():
                self._credentials.set(settings.provider, api_key.strip())
            else:
                self._credentials.clear(settings.provider)
        self._apply_llm_settings(settings)
        log.info("settings.llm_saved", provider=settings.provider, model=settings.model)
        self._broadcast(await self.llm_settings_message())
        await self.check_llm_setup()
        self._broadcast(self._status())

    async def test_llm(self) -> LlmTestMessage:
        """One tiny real request, so users know the key and model work before summarizing."""
        cfg = self._settings.llm
        try:
            await check_llm(cfg, self._credentials.get(cfg.provider))
            llm = self._llm_factory(cfg, self._credentials.get(cfg.provider))
            await asyncio.wait_for(llm.ainvoke("Reply with the single word OK."), timeout=30)
        except TimeoutError:
            return LlmTestMessage(
                type="llm_test", ok=False, message=f"{provider_name(cfg)} didn't answer in 30 s."
            )
        except Exception as err:
            return LlmTestMessage(type="llm_test", ok=False, message=str(explain_error(err, cfg)))
        return LlmTestMessage(
            type="llm_test", ok=True, message=f"Connected to {provider_name(cfg)} ({cfg.model})."
        )

    # --- speech settings (Settings → Speech) ------------------------------------------------

    async def load_saved_speech_settings(self) -> None:
        """Apply the speech model/language saved in the app; they override config.toml."""
        try:
            raw = await self._store.get_setting(STT_SETTINGS_KEY)
        except StorageError as err:
            log.warning("settings.load_failed", error=str(err))
            return
        if raw is None:
            return
        try:
            saved = SpeechSettings.model_validate_json(raw)
        except ValueError:
            log.warning("settings.invalid_saved_speech_settings")
            return
        self._apply_speech_settings(saved)

    def _apply_speech_settings(self, saved: SpeechSettings) -> None:
        stt = self._settings.stt.model_copy(update=saved.model_dump())
        self._settings = self._settings.model_copy(update={"stt": stt})
        self._transcriber.configure(stt)

    async def speech_settings_message(self) -> SpeechSettingsMessage:
        models_dir = self._settings.paths.resolved_models_dir()
        current = self._settings.stt.model
        infos = list(catalog.SPEECH_MODELS)
        if all(m.name != current for m in infos):  # a custom model from config.toml
            infos.append(catalog.SpeechModelInfo(current, current, 0, "Set in config.toml."))

        def options() -> list[SpeechModelOption]:
            return [
                SpeechModelOption(
                    name=m.name,
                    label=m.label,
                    size_mb=m.size_mb,
                    description=m.description,
                    english_only=m.english_only or catalog.is_english_only(m.name),
                    downloaded=catalog.is_downloaded(m.name, models_dir),
                )
                for m in infos
            ]

        return SpeechSettingsMessage(
            type="speech_settings",
            settings=SpeechSettings(model=current, language=self._settings.stt.language),
            models=await asyncio.to_thread(options),
            languages=[
                LanguageOption(code=code, name=name)
                for code, name in sorted(catalog.LANGUAGES.items(), key=lambda kv: kv[1])
            ],
        )

    async def save_speech_settings(self, settings: SpeechSettings) -> None:
        """Save the speech model and language. The model starts downloading/loading now (if
        it isn't ready yet); a new language applies from the next sentence."""
        model_changed = settings.model != self._settings.stt.model
        if model_changed and self._state != "idle":
            raise SessionError("session_busy", "Stop the recording before changing the model.")
        if model_changed and self._model_task is not None and not self._model_task.done():
            raise SessionError(
                "session_busy", "Wait until the current speech model has finished loading."
            )
        if catalog.is_english_only(settings.model) and settings.language not in (None, "en"):
            name = catalog.LANGUAGES[settings.language or "en"]
            raise SessionError(
                "bad_message",
                f"{_model_label(settings.model)} only understands English. Pick another speech "
                f"model to transcribe {name}.",
            )
        try:
            await self._store.set_setting(STT_SETTINGS_KEY, settings.model_dump_json())
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        self._apply_speech_settings(settings)
        log.info("settings.stt_saved", model=settings.model, language=settings.language)
        if model_changed:
            self._model_task, self._speech_model = None, None
        self.warm_up()  # choosing a model (also during first-run setup) means: get it ready
        self._broadcast(await self.speech_settings_message())
        self._broadcast(self._status())

    # --- first run ----------------------------------------------------------------------------

    async def finish_onboarding(self) -> None:
        try:
            await self._store.set_setting(ONBOARDED_KEY, "1")
        except StorageError as err:
            raise SessionError("storage_failed", str(err)) from None
        self._onboarded = True
        self.warm_up()  # no-op if the model was already picked (and is loading) during setup
        self._broadcast(self._status())

    async def capture_permission(
        self, action: str, platform_name: str = sys.platform
    ) -> CapturePermissionMessage:
        try:
            if action == "request":
                await asyncio.to_thread(capture_permission.request, platform_name)
            elif action == "open_settings":
                capture_permission.open_settings(platform_name)
            state, message = await asyncio.to_thread(capture_permission.check, platform_name)
        except Exception as err:
            log.warning("capture.permission_check_failed", error=str(err))
            state, message = "unknown", f"Couldn't check the audio permission: {err}"
        return CapturePermissionMessage(type="capture_permission", state=state, message=message)

    # --- diagnostics --------------------------------------------------------------------------

    async def diagnostics(self) -> DiagnosticsMessage:
        """A report to paste into a bug report. Never includes keys or transcript text."""
        cfg = self._settings
        models_dir = cfg.paths.resolved_models_dir()
        downloaded = await asyncio.to_thread(catalog.is_downloaded, cfg.stt.model, models_dir)
        try:
            sessions: int | str = len(await self._store.list_sessions())
        except StorageError as err:
            sessions = f"unavailable ({err})"
        path = logfile.log_file()
        lines = [
            f"Scribely {__version__}",
            f"OS: {platform.platform()} ({platform.machine()})",
            f"Python: {platform.python_version()}",
            f"State: {self._state}",
            f"Capture backend: {cfg.capture.backend}",
            f"Speech model: {cfg.stt.model} ({'downloaded' if downloaded else 'not downloaded'}), "
            f"device {cfg.stt.device}, language {cfg.stt.language or 'auto'}",
            f"Speech model state: {self._speech_model.state if self._speech_model else 'idle'}",
            f"Notes model: {provider_name(cfg.llm)} · {cfg.llm.model} "
            f"(API key: {self._credentials.source(cfg.llm.provider)})",
            f"Notes issue: {self._llm_issue or 'none'}",
            f"Sessions: {sessions}",
            f"Data folder: {cfg.paths.resolved_data_dir()}",
            f"Log file: {path or 'off'}",
            "",
            "--- recent log ---",
            *logfile.tail(),
        ]
        return DiagnosticsMessage(
            type="diagnostics", text="\n".join(lines), log_path=str(path) if path else None
        )


def _model_label(name: str) -> str:
    return next((m.label for m in catalog.SPEECH_MODELS if m.name == name), name)


def _level(rms: float) -> float:
    """RMS amplitude -> 0..1 on a dB scale (LEVEL_FLOOR_DB and below read as silence)."""
    db = 20 * math.log10(rms) if rms > 0 else LEVEL_FLOOR_DB
    return min(1.0, max(0.0, (db - LEVEL_FLOOR_DB) / -LEVEL_FLOOR_DB))
