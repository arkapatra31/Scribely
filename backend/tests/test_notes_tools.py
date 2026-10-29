import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from scribely.config import LLMConfig, PathsConfig, Settings, SttConfig
from scribely.credentials import Credentials
from scribely.export import export_filename, render_session_html
from scribely.models import (
    NoteDoc,
    NoteSection,
    ServerMessage,
    Session,
    SessionNotes,
    TranscriptSegment,
)
from scribely.pipeline.schemas import DraftNotes, DraftSection
from scribely.session import LiveSessionManager, SessionError
from scribely.session.store import MIGRATIONS, SessionStore
from tests.fake_llm import FakeLLM
from tests.stt_fakes import EnergyVAD, LoadableFakeTranscriber
from tests.test_live_session import drain, file_capture, wait_idle, wait_notes

T0 = datetime(2026, 10, 29, 9, 5, tzinfo=UTC)
SESSION = Session(id="s1", title=None, status="stopped", started_at=T0, ended_at=T0)
SEGMENTS = [
    TranscriptSegment(session_id="s1", index=0, start=0, end=4, text="Cells need <energy> & ATP."),
    TranscriptSegment(
        session_id="s1", index=1, start=65, end=70, text="Glycolysis splits glucose."
    ),
]
NOTES = SessionNotes(
    session_id="s1",
    doc=NoteDoc(
        title='Respiration: "Glycolysis"/Krebs',
        summary="How cells make ATP.",
        sections=[NoteSection(heading="Glycolysis", points=["Splits glucose"], start=60, end=70)],
    ),
    provider="anthropic",
    model="claude-sonnet-5-5",
    created_at=T0,
    style="qa",
    edited=True,
)


# --- HTML export ----------------------------------------------------------------------------


def test_html_is_standalone_escaped_and_linked() -> None:
    html = render_session_html(SESSION, SEGMENTS, NOTES)
    assert "<title>Respiration: &#34;Glycolysis&#34;/Krebs</title>" in html
    assert "Cells need &lt;energy&gt; &amp; ATP." in html  # transcript text is escaped
    assert 'href="#t1"' in html and 'id="t1"' in html  # section time links to the transcript line
    assert "1:00 \u2013 1:10" in html  # en dash
    assert "Questions &amp; answers" in html and "Anthropic (claude-sonnet-5-5), edited" in html
    assert "<script" not in html and "http" not in html.split("<main>")[1]  # no external assets


def test_transcript_only_export_opens_the_transcript() -> None:
    html = render_session_html(SESSION, SEGMENTS, None)
    assert "<details open>" in html and "Summary" not in html


def test_export_filenames_are_safe_and_never_overwrite(tmp_path: Path) -> None:
    first = export_filename(SESSION, NOTES, tmp_path)
    assert first.name.endswith(".html") and "/" not in first.name.replace(str(tmp_path), "")
    assert ":" not in first.name and '"' not in first.name
    first.write_text("x")
    second = export_filename(SESSION, NOTES, tmp_path)
    assert second != first and second.name.endswith("(2).html")
    untitled = export_filename(SESSION, None, tmp_path).name
    assert "Session at " in untitled and " at 0" not in untitled


# --- manager: export, edit, restructure ------------------------------------------------------


def restructured(schema: type[BaseModel], prompt: str) -> BaseModel:
    assert "study questions and answers" in prompt and '"Glycolysis"' in prompt
    return DraftNotes(
        title="Respiration Q&A",
        summary="Short.",
        sections=[
            DraftSection(
                heading="What does glycolysis do?",
                points=["Splits glucose"],
                start_seconds=60,
                end_seconds=999,
            )
        ],
    )


def manager(tmp_path: Path, llm: FakeLLM | None = None) -> LiveSessionManager:
    fake = llm or FakeLLM(restructured)
    return LiveSessionManager(
        Settings(
            stt=SttConfig(partial_interval_seconds=0),
            llm=LLMConfig(azure_endpoint="https://example.openai.azure.com/"),
            paths=PathsConfig(data_dir=tmp_path / "data"),
        ),
        store=SessionStore.open(tmp_path / "scribely.db"),
        transcriber=LoadableFakeTranscriber(),
        capture_factory=file_capture(tmp_path),
        vad_factory=EnergyVAD,
        llm_factory=lambda cfg, key: fake.as_chat_model(),
        credentials=Credentials(),
    )


async def recorded_with_notes(m: LiveSessionManager) -> str:
    session = await m.start("Bio")
    await wait_idle(m)
    await m._store.save_notes(
        NOTES.model_copy(update={"session_id": session.id, "style": "standard", "edited": False})
    )
    return session.id


def test_export_session_writes_html_into_exports(tmp_path: Path) -> None:
    async def run() -> Any:
        m = manager(tmp_path)
        sid = await recorded_with_notes(m)
        return await m.export_session(sid)

    exported = asyncio.run(run())
    path = Path(exported.path)
    assert path.parent == tmp_path / "data" / "exports" and path.is_file()
    assert "speech 1.0s" in path.read_text(encoding="utf-8")


def test_reveal_only_allows_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[list[str]] = []
    monkeypatch.setattr(
        "scribely.session.live.subprocess.Popen", lambda cmd, **kw: opened.append(cmd)
    )

    async def run() -> None:
        m = manager(tmp_path)
        sid = await recorded_with_notes(m)
        exported = await m.export_session(sid)
        await m.reveal_export(exported.path)
        with pytest.raises(SessionError, match="no longer exists"):
            await m.reveal_export(str(tmp_path / "scribely.db"))

    asyncio.run(run())
    assert (len(opened) == 1 and opened[0][-1].endswith(".html")) or "exports" in opened[0][-1]


def test_edit_marks_notes_edited_and_broadcasts(tmp_path: Path) -> None:
    async def run() -> tuple[Any, list[ServerMessage]]:
        m = manager(tmp_path)
        sid = await recorded_with_notes(m)
        queue = m.subscribe()
        drain(queue)
        doc = NOTES.doc.model_copy(update={"title": "My own title"})
        saved = await m.update_notes(sid, doc)
        with pytest.raises(SessionError) as exc:
            await m.update_notes("missing", doc)
        assert exc.value.code == "not_found"
        return saved, drain(queue)

    saved, messages = asyncio.run(run())
    assert saved.edited and saved.doc.title == "My own title"
    assert any(msg.type == "notes" and msg.notes.doc.title == "My own title" for msg in messages)


def test_restructure_rewrites_current_notes(tmp_path: Path) -> None:
    async def run() -> list[ServerMessage]:
        m = manager(tmp_path)
        sid = await recorded_with_notes(m)
        queue = m.subscribe()
        drain(queue)
        await m.restructure(sid, "qa")
        return await wait_notes(queue)

    messages = asyncio.run(run())
    notes = [msg for msg in messages if msg.type == "notes"][-1].notes
    assert notes.style == "qa" and not notes.edited
    assert notes.doc.sections[0].heading == "What does glycolysis do?"
    assert notes.doc.sections[0].end == 70  # clamped to the original notes' span


def test_restructure_needs_notes(tmp_path: Path) -> None:
    async def run() -> None:
        m = manager(tmp_path)
        session = await m.start()
        await wait_idle(m)
        with pytest.raises(SessionError, match="Summarize this session first"):
            await m.restructure(session.id, "outline")

    asyncio.run(run())


def test_migration_v4_keeps_existing_notes(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    for number, script in enumerate(MIGRATIONS[:3], start=1):
        conn.executescript(f"BEGIN; {script}; PRAGMA user_version = {number}; COMMIT;")
    conn.execute("INSERT INTO sessions VALUES ('s1', NULL, 'stopped', ?, NULL)", (T0.isoformat(),))
    conn.execute(
        "INSERT INTO notes VALUES ('s1', ?, 'openai', 'gpt-4o', ?)",
        (NOTES.doc.model_dump_json(), T0.isoformat()),
    )
    conn.commit()
    conn.close()
    store = SessionStore.open(db)
    notes = asyncio.run(store.get_notes("s1"))
    assert notes is not None and notes.style == "standard" and notes.edited is False
    store.close()
