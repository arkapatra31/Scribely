"""Jinja2 -> standalone HTML. The output has no external assets, so it opens anywhere."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from scribely import __version__
from scribely.models import Session, SessionNotes, TranscriptSegment

_PROVIDERS = {
    "azure_openai": "Azure OpenAI",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "ollama": "Ollama",
}
_STYLES = {
    "standard": "",
    "outline": "Study outline",
    "qa": "Questions & answers",
    "condensed": "Condensed",
}

_env = Environment(
    loader=PackageLoader("scribely.export", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def clock(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


_env.filters["clock"] = clock


def session_title(session: Session) -> str:
    if session.title:
        return session.title
    # %-I isn't portable (Windows), so trim the hour's leading zero by hand.
    return f"Session at {session.started_at.astimezone():%I:%M %p}".replace(" at 0", " at ")


def render_session_html(
    session: Session, segments: list[TranscriptSegment], notes: SessionNotes | None
) -> str:
    duration = segments[-1].end if segments else 0.0
    return _env.get_template("session.html.j2").render(
        session=session,
        title=notes.doc.title if notes else session_title(session),
        session_title=session_title(session),
        started=session.started_at.astimezone(),
        duration=clock(duration),
        segments=segments,
        notes=notes,
        provider=_PROVIDERS.get(notes.provider, notes.provider) if notes else None,
        style=_STYLES.get(notes.style, "") if notes else "",
        version=__version__,
        exported=datetime.now().astimezone(),
    )


def export_filename(
    session: Session, notes: SessionNotes | None, directory: Path, suffix: str = ".html"
) -> Path:
    """``<date> <title><suffix>`` in ``directory``, never overwriting an existing file."""
    title = notes.doc.title if notes else session_title(session)
    slug = _slug(title) or "session"
    stem = f"{session.started_at.astimezone():%Y-%m-%d} {slug}"
    path = directory / f"{stem}{suffix}"
    n = 2
    while path.exists():
        path = directory / f"{stem} ({n}){suffix}"
        n += 1
    return path


def _slug(text: str, limit: int = 80) -> str:
    """A filename-safe version of ``text`` that stays readable (keeps spaces and case)."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", text)  # characters Windows/macOS reject
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:limit].rstrip(" .")
