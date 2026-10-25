"""Pydantic schemas for everything that crosses the WebSocket/HTTP boundary.

TypeScript types are generated from this module (``pnpm gen:schemas``);
the frontend never hand-writes them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scribely.config import LLMProvider

# interrupted: the app quit or crashed mid-recording; saved segments were recovered.
SessionStatus = Literal["recording", "stopped", "interrupted", "failed"]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(Schema):
    status: Literal["ok"]
    version: str


class TranscriptSegment(Schema):
    session_id: str
    index: int = Field(ge=0, description="0-based position of the segment within its session.")
    start: float = Field(ge=0, description="Start offset in seconds from session start.")
    end: float = Field(ge=0, description="End offset in seconds from session start.")
    text: str

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must be >= start")
        return self


class Session(Schema):
    id: str
    title: str | None = None
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None = None

    @model_validator(mode="after")
    def _ended_after_started(self) -> Self:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must be >= started_at")
        return self


class SessionSummary(Schema):
    """A session as shown in the session list."""

    session: Session
    segment_count: int = Field(ge=0)
    duration: float = Field(ge=0, description="Seconds from session start to the last segment.")
    has_notes: bool = False


class NoteSection(Schema):
    heading: str = Field(description="Short title for this part of the lecture.")
    points: list[str] = Field(description="Concise note points, in lecture order.")
    start: float = Field(ge=0, description="Offset in seconds where this section begins.")
    end: float = Field(ge=0, description="Offset in seconds where this section ends.")

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must be >= start")
        return self


class NoteDoc(Schema):
    """Structured notes for one session."""

    title: str = Field(description="Title describing the whole session.")
    summary: str = Field(description="A few sentences summarising the session.")
    sections: list[NoteSection] = Field(description="Note sections in chronological order.")


class SessionNotes(Schema):
    """Generated notes for a session, with what produced them."""

    session_id: str
    doc: NoteDoc
    provider: str
    model: str
    created_at: datetime


# --- WebSocket protocol (/ws) ------------------------------------------------------------
# Every message is a JSON object with a "type" discriminator.

BackendState = Literal["idle", "loading_model", "recording", "stopping"]
ErrorCode = Literal[
    "capture_permission",
    "capture_failed",
    "model_failed",
    "already_recording",
    "not_recording",
    "bad_message",
    "not_found",
    "session_busy",
    "storage_failed",
    "llm_failed",
    "internal",
]
NotesJobState = Literal["running", "done", "failed"]
# Where the API key for a provider comes from. Keys are never stored: "session" means
# entered in Settings since the backend started (memory only).
KeySource = Literal["session", "env", "missing", "not_needed"]


class StartCommand(Schema):
    """Client -> server: start a recording session."""

    type: Literal["start"]
    title: str | None = None


class StopCommand(Schema):
    """Client -> server: stop the current session."""

    type: Literal["stop"]


class ListSessionsCommand(Schema):
    """Client -> server: ask for the session list (also sent automatically on connect)."""

    type: Literal["list_sessions"]


class OpenSessionCommand(Schema):
    """Client -> server: load a saved session's transcript."""

    type: Literal["open_session"]
    session_id: str


class RenameSessionCommand(Schema):
    type: Literal["rename_session"]
    session_id: str
    title: str = Field(max_length=200)


class DeleteSessionCommand(Schema):
    type: Literal["delete_session"]
    session_id: str


class SummarizeCommand(Schema):
    """Client -> server: generate (or regenerate) notes for a stopped session."""

    type: Literal["summarize"]
    session_id: str


class LlmSettings(Schema):
    """The notes LLM, as edited in the Settings panel (API keys travel separately)."""

    provider: LLMProvider
    model: str = Field(min_length=1, max_length=200)
    azure_endpoint: str | None = Field(default=None, max_length=500)
    azure_deployment: str | None = Field(default=None, max_length=200)
    azure_api_version: str = Field(min_length=1, max_length=50)
    ollama_host: str = Field(min_length=1, max_length=500)
    temperature: float = Field(ge=0.0, le=2.0)

    @field_validator(
        "model", "azure_endpoint", "azure_deployment", "azure_api_version", "ollama_host"
    )
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("azure_endpoint")
    @classmethod
    def _https(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("The Azure endpoint must start with https://")
        return value


class GetLlmSettingsCommand(Schema):
    type: Literal["get_llm_settings"]


class SaveLlmSettingsCommand(Schema):
    """Client -> server: save LLM settings. ``api_key``: None keeps the key already entered
    this session, "" forgets it, anything else replaces it. Keys are kept in memory only and
    never stored."""

    type: Literal["save_llm_settings"]
    settings: LlmSettings
    api_key: str | None = Field(default=None, max_length=1000)


class TestLlmCommand(Schema):
    """Client -> server: make one tiny request with the saved settings."""

    type: Literal["test_llm"]


class StatusMessage(Schema):
    """Server -> client: backend state; sent on connect and on every change."""

    type: Literal["status"]
    state: BackendState
    session: Session | None = None
    model: str = Field(description="Configured speech model name.")
    llm_issue: str | None = Field(
        default=None, description="Why notes can't be generated right now, if known."
    )


class TranscriptSnapshot(Schema):
    """Server -> client: final segments of the current/last session, sent on connect."""

    type: Literal["transcript_snapshot"]
    segments: list[TranscriptSegment]


class TranscriptPartialMessage(Schema):
    """Server -> client: live hypothesis for in-progress speech; replaced by later messages."""

    type: Literal["transcript_partial"]
    session_id: str
    start: float
    end: float
    text: str


class TranscriptFinalMessage(Schema):
    """Server -> client: a finished transcript segment."""

    type: Literal["transcript_final"]
    segment: TranscriptSegment


class SessionsMessage(Schema):
    """Server -> client: all saved sessions, newest first; sent on connect and on changes."""

    type: Literal["sessions"]
    sessions: list[SessionSummary]


class SessionOpenedMessage(Schema):
    """Server -> client: reply to open_session."""

    type: Literal["session_opened"]
    session: Session
    segments: list[TranscriptSegment]
    notes: SessionNotes | None = None


class NotesJobMessage(Schema):
    """Server -> client: progress of a summarize request (broadcast)."""

    type: Literal["notes_job"]
    session_id: str
    state: NotesJobState
    message: str = Field(description="Plain-language progress or failure text.")


class NotesMessage(Schema):
    """Server -> client: finished notes for a session (broadcast)."""

    type: Literal["notes"]
    notes: SessionNotes


class LlmSettingsMessage(Schema):
    """Server -> client: current LLM settings, without any secrets."""

    type: Literal["llm_settings"]
    settings: LlmSettings
    key_sources: dict[str, KeySource]
    suggested_models: dict[str, list[str]]
    ollama_models: list[str] = Field(description="Models pulled in Ollama, if it's reachable.")


class LlmTestMessage(Schema):
    type: Literal["llm_test"]
    ok: bool
    message: str


class ErrorMessage(Schema):
    """Server -> client: a plain-language problem to show the user."""

    type: Literal["error"]
    code: ErrorCode
    message: str


ClientMessage = Annotated[
    StartCommand
    | StopCommand
    | ListSessionsCommand
    | OpenSessionCommand
    | RenameSessionCommand
    | DeleteSessionCommand
    | SummarizeCommand
    | GetLlmSettingsCommand
    | SaveLlmSettingsCommand
    | TestLlmCommand,
    Field(discriminator="type"),
]
ServerMessage = Annotated[
    StatusMessage
    | TranscriptSnapshot
    | TranscriptPartialMessage
    | TranscriptFinalMessage
    | SessionsMessage
    | SessionOpenedMessage
    | NotesJobMessage
    | NotesMessage
    | LlmSettingsMessage
    | LlmTestMessage
    | ErrorMessage,
    Field(discriminator="type"),
]


class WsProtocol(Schema):
    """Never sent. Exists so the generated TypeScript includes the message unions:
    use ``WsProtocol["client"]`` / ``WsProtocol["server"]`` on the frontend."""

    client: ClientMessage
    server: ServerMessage
