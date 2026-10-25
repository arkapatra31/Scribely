"""SQLite (WAL) persistence for sessions and transcript segments.

All database work runs on one dedicated thread (sqlite3 connections are thread-bound),
so callers on the event loop never block. Segments are queued in memory and written in
batches by ``flush()``; the session manager flushes about once a second while recording,
so a crash loses at most that much transcript.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

import structlog

from scribely.models import (
    NoteDoc,
    Session,
    SessionNotes,
    SessionStatus,
    SessionSummary,
    TranscriptSegment,
)

T = TypeVar("T")
log = structlog.get_logger(__name__)

# Each entry upgrades the schema by one version (PRAGMA user_version). Never edit a released
# entry; append a new one.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE sessions (
        id          TEXT PRIMARY KEY,
        title       TEXT,
        status      TEXT NOT NULL,
        started_at  TEXT NOT NULL,
        ended_at    TEXT
    );
    CREATE TABLE segments (
        session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        idx         INTEGER NOT NULL,
        start       REAL NOT NULL,
        end         REAL NOT NULL,
        text        TEXT NOT NULL,
        PRIMARY KEY (session_id, idx)
    );
    CREATE INDEX sessions_started_at ON sessions(started_at DESC);
    """,
    """
    CREATE TABLE notes (
        session_id  TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
        doc         TEXT NOT NULL,
        provider    TEXT NOT NULL,
        model       TEXT NOT NULL,
        created_at  TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE settings (
        key    TEXT PRIMARY KEY,
        value  TEXT NOT NULL
    );
    """,
]


class StorageError(Exception):
    """Database problem with a plain-language message safe to show the user."""


class SessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scribely-db")
        self._conn: sqlite3.Connection | None = None
        self._pending: list[TranscriptSegment] = []

    @classmethod
    def open(cls, path: Path) -> SessionStore:
        """Open (creating/migrating if needed) and recover sessions cut off by a crash."""
        store = cls(path)
        try:
            store._executor.submit(store._open_blocking).result()
        except sqlite3.Error as err:
            store._executor.shutdown(wait=False)
            raise StorageError(
                f"Couldn't open the Scribely database at {path}: {err}. Check that the folder "
                "is writable and the disk isn't full."
            ) from None
        except OSError as err:
            store._executor.shutdown(wait=False)
            raise StorageError(
                f"Couldn't create the Scribely data folder {path.parent}: {err.strerror}."
            ) from None
        return store

    def close(self) -> None:
        def close_blocking() -> None:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

        self._executor.submit(close_blocking).result()
        self._executor.shutdown(wait=True)

    # --- writes -----------------------------------------------------------------------------

    async def create_session(self, session: Session) -> None:
        await self._run(self._upsert_session, session)

    async def update_session(self, session: Session) -> None:
        await self._run(self._upsert_session, session)

    def queue_segment(self, segment: TranscriptSegment) -> None:
        """Buffer a segment for the next ``flush()`` (call from the event loop)."""
        self._pending.append(segment)

    async def flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        try:
            await self._run(self._insert_segments, batch)
        except StorageError:
            self._pending[:0] = batch  # keep them for the next attempt
            raise

    async def rename_session(self, session_id: str, title: str | None) -> Session | None:
        return await self._run(self._rename_blocking, session_id, title)

    async def delete_session(self, session_id: str) -> bool:
        return await self._run(self._delete_blocking, session_id)

    async def get_setting(self, key: str) -> str | None:
        return await self._run(self._get_setting_blocking, key)

    async def set_setting(self, key: str, value: str) -> None:
        await self._run(self._set_setting_blocking, key, value)

    async def save_notes(self, notes: SessionNotes) -> None:
        await self._run(self._save_notes_blocking, notes)

    # --- reads ------------------------------------------------------------------------------

    async def get_notes(self, session_id: str) -> SessionNotes | None:
        return await self._run(self._get_notes_blocking, session_id)

    async def list_sessions(self) -> list[SessionSummary]:
        return await self._run(self._list_blocking)

    async def get_session(self, session_id: str) -> tuple[Session, list[TranscriptSegment]] | None:
        return await self._run(self._get_blocking, session_id)

    # --- internals (db thread) --------------------------------------------------------------

    async def _run(self, fn: Callable[..., T], *args: object) -> T:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self._executor, fn, *args)
        except sqlite3.Error as err:
            log.error("storage.error", error=str(err))
            raise StorageError(f"Couldn't save or load sessions: {err}.") from None

    @property
    def _db(self) -> sqlite3.Connection:
        assert self._conn is not None, "store is closed"
        return self._conn

    def _open_blocking(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, isolation_level=None)  # explicit transactions
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # durable across app crashes in WAL mode
        conn.execute("PRAGMA foreign_keys=ON")
        self._conn = conn
        self._migrate()
        self._recover_interrupted()

    def _migrate(self) -> None:
        version = int(self._db.execute("PRAGMA user_version").fetchone()[0])
        if version > len(MIGRATIONS):
            raise sqlite3.DatabaseError(
                f"database schema v{version} is newer than this version of Scribely supports"
            )
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            # executescript commits any open transaction first, so wrap explicitly.
            self._db.executescript(f"BEGIN; {script}; PRAGMA user_version = {number}; COMMIT;")
            log.info("storage.migrated", version=number)

    def _recover_interrupted(self) -> None:
        rows = self._db.execute(
            "SELECT s.id, s.started_at, MAX(g.end) AS last_end FROM sessions s "
            "LEFT JOIN segments g ON g.session_id = s.id "
            "WHERE s.status = 'recording' GROUP BY s.id"
        ).fetchall()
        for row in rows:
            ended = datetime.fromisoformat(row["started_at"]) + timedelta(
                seconds=row["last_end"] or 0.0
            )
            self._db.execute(
                "UPDATE sessions SET status = 'interrupted', ended_at = ? WHERE id = ?",
                (ended.isoformat(), row["id"]),
            )
            log.warning("storage.recovered_interrupted", session_id=row["id"])

    def _upsert_session(self, s: Session) -> None:
        self._db.execute(
            "INSERT INTO sessions (id, title, status, started_at, ended_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "title = excluded.title, status = excluded.status, ended_at = excluded.ended_at",
            (
                s.id,
                s.title,
                s.status,
                s.started_at.isoformat(),
                s.ended_at.isoformat() if s.ended_at else None,
            ),
        )

    def _insert_segments(self, batch: list[TranscriptSegment]) -> None:
        with self._transaction():
            self._db.executemany(
                "INSERT OR REPLACE INTO segments (session_id, idx, start, end, text) "
                "VALUES (?, ?, ?, ?, ?)",
                [(g.session_id, g.index, g.start, g.end, g.text) for g in batch],
            )

    def _rename_blocking(self, session_id: str, title: str | None) -> Session | None:
        self._db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        found = self._get_blocking(session_id)
        return found[0] if found else None

    def _delete_blocking(self, session_id: str) -> bool:
        cur = self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0

    def _list_blocking(self) -> list[SessionSummary]:
        rows = self._db.execute(
            "SELECT s.*, COUNT(g.idx) AS segment_count, COALESCE(MAX(g.end), 0) AS duration, "
            "EXISTS(SELECT 1 FROM notes n WHERE n.session_id = s.id) AS has_notes "
            "FROM sessions s LEFT JOIN segments g ON g.session_id = s.id "
            "GROUP BY s.id ORDER BY s.started_at DESC"
        ).fetchall()
        return [
            SessionSummary(
                session=_row_to_session(r),
                segment_count=r["segment_count"],
                duration=r["duration"],
                has_notes=bool(r["has_notes"]),
            )
            for r in rows
        ]

    def _get_setting_blocking(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def _set_setting_blocking(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _save_notes_blocking(self, notes: SessionNotes) -> None:
        self._db.execute(
            "INSERT INTO notes (session_id, doc, provider, model, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET doc = excluded.doc, "
            "provider = excluded.provider, model = excluded.model, "
            "created_at = excluded.created_at",
            (
                notes.session_id,
                notes.doc.model_dump_json(),
                notes.provider,
                notes.model,
                notes.created_at.isoformat(),
            ),
        )

    def _get_notes_blocking(self, session_id: str) -> SessionNotes | None:
        row = self._db.execute("SELECT * FROM notes WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return SessionNotes(
            session_id=session_id,
            doc=NoteDoc.model_validate_json(row["doc"]),
            provider=row["provider"],
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _get_blocking(self, session_id: str) -> tuple[Session, list[TranscriptSegment]] | None:
        row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        segments = [
            TranscriptSegment(
                session_id=session_id,
                index=g["idx"],
                start=g["start"],
                end=g["end"],
                text=g["text"],
            )
            for g in self._db.execute(
                "SELECT * FROM segments WHERE session_id = ? ORDER BY idx", (session_id,)
            )
        ]
        return _row_to_session(row), segments

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[None]:
        self._db.execute("BEGIN")
        try:
            yield
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        self._db.execute("COMMIT")


def _row_to_session(row: sqlite3.Row) -> Session:
    status: SessionStatus = row["status"]
    return Session(
        id=row["id"],
        title=row["title"],
        status=status,
        started_at=datetime.fromisoformat(row["started_at"]),
        ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
    )
