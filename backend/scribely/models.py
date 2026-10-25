"""Pydantic schemas for everything that crosses the WebSocket/HTTP boundary.

TypeScript types are generated from this module (``pnpm gen:schemas``);
the frontend never hand-writes them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SessionStatus = Literal["recording", "stopped", "generating", "ready", "failed"]


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
    """Structured notes for one session; also the LLM's structured-output schema."""

    title: str = Field(description="Title describing the whole session.")
    summary: str = Field(description="A few sentences summarising the session.")
    sections: list[NoteSection] = Field(description="Note sections in chronological order.")
