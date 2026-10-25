"""Live recording sessions: capture -> streaming STT -> broadcast to WebSocket clients.

One session records at a time. Final segments of the current/last session are kept in
memory (the rolling window the live UI is fed from); persistence comes in Phase 3.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

import structlog

from scribely.capture import AudioCapture, CaptureError, CapturePermissionError, create_capture
from scribely.config import Settings
from scribely.models import (
    BackendState,
    ErrorCode,
    ErrorMessage,
    ServerMessage,
    Session,
    SessionStatus,
    StatusMessage,
    TranscriptFinalMessage,
    TranscriptPartialMessage,
    TranscriptSegment,
    TranscriptSnapshot,
)
from scribely.stt import SileroVAD, SpeechDetector, StreamingTranscriber, STTError
from scribely.stt.transcriber import Transcriber, WhisperTranscriber

SUBSCRIBER_QUEUE_SIZE = 1000

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
        transcriber: LoadableTranscriber | None = None,
        capture_factory: Callable[[], AudioCapture] | None = None,
        vad_factory: Callable[[], SpeechDetector] | None = None,
    ) -> None:
        self._settings = settings
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
            type="status", state=self._state, session=self._session, model=self._settings.stt.model
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
            self._session, self._segments, self._capture = session, [], capture
            self._run_failed = False
            self._run_task = asyncio.create_task(self._run(capture, session))
            self._set_state("recording")
            self._broadcast(TranscriptSnapshot(type="transcript_snapshot", segments=[]))
            log.info("session.started", session_id=session.id)
            return session

    async def stop(self) -> Session:
        async with self._lock:
            if self._state != "recording" or self._capture is None or self._run_task is None:
                raise SessionError("not_recording", "Nothing is being recorded.")
            self._set_state("stopping")
            await self._capture.stop()
            await self._run_task  # drains the last segment; handles its own errors
            return self._end_session("failed" if self._run_failed else "stopped")

    async def shutdown(self) -> None:
        if self._state == "recording":
            await self.stop()

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
                await capture.stop()
                self._end_session("stopped")
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
            await capture.stop()
            if self._state == "recording":  # not already being stopped by stop()
                self._end_session("failed")

    def _end_session(self, status: SessionStatus) -> Session:
        assert self._session is not None
        session = self._session.model_copy(update={"status": status, "ended_at": datetime.now(UTC)})
        self._session, self._capture, self._run_task = session, None, None
        self._set_state("idle")
        log.info(
            "session.ended", session_id=session.id, status=status, segments=len(self._segments)
        )
        return session
