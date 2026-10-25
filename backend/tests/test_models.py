from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from scribely.models import NoteDoc, NoteSection, Session, TranscriptSegment


def test_segment_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError, match="end must be >= start"):
        TranscriptSegment(session_id="s", index=0, start=5.0, end=1.0, text="hi")


def test_session_rejects_end_before_start() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="ended_at"):
        Session(id="s", status="stopped", started_at=now, ended_at=now - timedelta(seconds=1))


def test_notedoc_round_trips_json() -> None:
    doc = NoteDoc(
        title="T",
        summary="S",
        sections=[NoteSection(heading="H", points=["a"], start=0, end=10)],
    )
    assert NoteDoc.model_validate_json(doc.model_dump_json()) == doc


def test_notedoc_schema_forbids_extra_fields() -> None:
    # Strict structured-output providers require additionalProperties: false.
    schema = NoteDoc.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["NoteSection"]["additionalProperties"] is False
