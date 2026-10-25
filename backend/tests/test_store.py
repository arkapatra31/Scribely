import asyncio
import sqlite3
import subprocess
import sys
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scribely.models import Session, TranscriptSegment
from scribely.session.store import SessionStore, StorageError

T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


def session(id: str = "s1", minutes: int = 0, status: str = "recording") -> Session:
    return Session(id=id, status=status, started_at=T0 + timedelta(minutes=minutes))


def seg(i: int, session_id: str = "s1") -> TranscriptSegment:
    return TranscriptSegment(
        session_id=session_id, index=i, start=i * 2.0, end=i * 2.0 + 1.5, text=f"line {i}"
    )


def test_roundtrip_and_batched_segments(tmp_path: Path) -> None:
    store = SessionStore.open(tmp_path / "db" / "scribely.db")

    async def run() -> None:
        await store.create_session(session())
        for i in range(3):
            store.queue_segment(seg(i))
        assert (await store.get_session("s1"))[1] == []  # type: ignore[index]
        await store.flush()
        found = await store.get_session("s1")
        assert found is not None
        stored, segments = found
        assert stored == session()
        assert [g.text for g in segments] == ["line 0", "line 1", "line 2"]
        assert await store.get_session("nope") is None

    asyncio.run(run())
    store.close()


def test_list_is_newest_first_with_counts(tmp_path: Path) -> None:
    store = SessionStore.open(tmp_path / "scribely.db")

    async def run() -> list[tuple[str, int, float]]:
        await store.create_session(session("old", 0, "stopped"))
        await store.create_session(session("new", 30, "stopped"))
        for i in range(4):
            store.queue_segment(seg(i, "old"))
        await store.flush()
        return [(s.session.id, s.segment_count, s.duration) for s in await store.list_sessions()]

    assert asyncio.run(run()) == [("new", 0, 0.0), ("old", 4, 7.5)]
    store.close()


def test_rename_and_delete_cascade(tmp_path: Path) -> None:
    store = SessionStore.open(tmp_path / "scribely.db")

    async def run() -> None:
        await store.create_session(session())
        store.queue_segment(seg(0))
        await store.flush()
        renamed = await store.rename_session("s1", "Bio 101")
        assert renamed is not None and renamed.title == "Bio 101"
        assert await store.rename_session("nope", "x") is None
        assert await store.delete_session("s1") is True
        assert await store.delete_session("s1") is False
        assert await store.list_sessions() == []

    asyncio.run(run())
    rows = sqlite3.connect(tmp_path / "scribely.db").execute("SELECT COUNT(*) FROM segments")
    assert rows.fetchone()[0] == 0
    store.close()


def test_uses_wal_and_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "scribely.db"
    store = SessionStore.open(path)
    asyncio.run(store.create_session(session(status="stopped")))
    store.close()
    assert sqlite3.connect(path).execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    store = SessionStore.open(path)
    assert len(asyncio.run(store.list_sessions())) == 1
    store.close()


def test_recording_killed_mid_session_is_recovered(tmp_path: Path) -> None:
    """DoD: a recording survives an app kill mid-session and reloads from SQLite."""
    path = tmp_path / "scribely.db"
    script = textwrap.dedent(
        f"""
        import asyncio, os
        from pathlib import Path
        from datetime import datetime, UTC
        from scribely.models import Session, TranscriptSegment
        from scribely.session.store import SessionStore

        async def main():
            store = SessionStore.open(Path({str(path)!r}))
            await store.create_session(Session(id="live", status="recording",
                                               started_at=datetime(2026, 10, 25, 9, 0, tzinfo=UTC)))
            for i in range(5):
                store.queue_segment(TranscriptSegment(session_id="live", index=i, start=i * 10.0,
                                                      end=i * 10.0 + 8, text=f"line {{i}}"))
            await store.flush()
            os._exit(9)  # hard kill: no close, no status update

        asyncio.run(main())
        """
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[1])
    assert result.returncode == 9

    store = SessionStore.open(path)
    found = asyncio.run(store.get_session("live"))
    assert found is not None
    recovered, segments = found
    assert recovered.status == "interrupted"
    assert recovered.ended_at == T0 + timedelta(seconds=48)
    assert len(segments) == 5
    store.close()


def test_newer_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "scribely.db"
    sqlite3.connect(path).execute("PRAGMA user_version = 99")
    with pytest.raises(StorageError, match="newer than this version"):
        SessionStore.open(path)


def test_unwritable_location_is_actionable(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    with pytest.raises(StorageError, match="Couldn't create the Scribely data folder"):
        SessionStore.open(blocker / "scribely.db")


def test_notes_roundtrip_has_notes_and_cascade(tmp_path: Path) -> None:
    from scribely.models import NoteDoc, NoteSection, SessionNotes

    store = SessionStore.open(tmp_path / "scribely.db")
    notes = SessionNotes(
        session_id="s1",
        doc=NoteDoc(
            title="T",
            summary="S",
            sections=[NoteSection(heading="H", points=["p"], start=0, end=1)],
        ),
        provider="azure_openai",
        model="gpt-4o",
        created_at=T0,
    )

    async def run() -> None:
        await store.create_session(session(status="stopped"))
        assert await store.get_notes("s1") is None
        assert (await store.list_sessions())[0].has_notes is False
        await store.save_notes(notes)
        await store.save_notes(notes.model_copy(update={"model": "gpt-4.1"}))  # regenerate
        saved = await store.get_notes("s1")
        assert saved is not None and saved.doc == notes.doc and saved.model == "gpt-4.1"
        assert (await store.list_sessions())[0].has_notes is True
        await store.delete_session("s1")
        assert await store.get_notes("s1") is None

    asyncio.run(run())
    store.close()
