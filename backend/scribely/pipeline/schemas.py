"""Schemas the LLM fills in. Deliberately lenient (no cross-field validators) so a slightly
off answer still parses; ``to_note_doc`` cleans it into the strict ``NoteDoc``."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from scribely.models import NoteDoc, NoteSection


class _LLMSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")  # strict structured-output modes require it


class DraftSection(_LLMSchema):
    heading: str = Field(description="Short, specific title for this part of the lecture.")
    points: list[str] = Field(description="2-6 concise note points, in the order discussed.")
    start_seconds: float = Field(description="Value of the [Ns] marker where this part begins.")
    end_seconds: float = Field(description="Value of the [Ns] marker where this part ends.")


class DraftSections(_LLMSchema):
    sections: list[DraftSection] = Field(description="Note sections in chronological order.")


class DraftNotes(_LLMSchema):
    title: str = Field(description="Title describing the whole lecture.")
    summary: str = Field(description="3-5 sentence summary of the whole lecture.")
    sections: list[DraftSection] = Field(description="Note sections in chronological order.")


def to_note_doc(draft: DraftNotes, duration: float) -> NoteDoc:
    sections = []
    for d in sorted(draft.sections, key=lambda s: s.start_seconds):
        points = [p.strip() for p in d.points if p.strip()]
        if not points:
            continue
        start = min(max(0.0, d.start_seconds), duration)
        end = min(max(start, d.end_seconds), duration)
        sections.append(NoteSection(heading=d.heading.strip(), points=points, start=start, end=end))
    return NoteDoc(title=draft.title.strip(), summary=draft.summary.strip(), sections=sections)
