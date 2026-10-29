"""PDF export via WeasyPrint, styled like the app (bundled Inter + Newsreader fonts)."""

from __future__ import annotations

import sys
from pathlib import Path

from scribely.export.html import render_session_html
from scribely.models import Session, SessionNotes, TranscriptSegment

FONTS_DIR = Path(__file__).parent / "fonts"


class PdfUnavailableError(Exception):
    """WeasyPrint's native libraries (Pango) are missing; the message says how to fix it."""


def render_session_pdf(
    session: Session, segments: list[TranscriptSegment], notes: SessionNotes | None
) -> bytes:
    html = render_session_html(session, segments, notes, template="session.pdf.j2")
    try:
        from weasyprint import HTML
    except OSError as err:  # raised while loading Pango/GObject
        raise PdfUnavailableError(_install_hint(err)) from None
    # base_url lets the template's @font-face rules find the bundled fonts.
    pdf: bytes = HTML(string=html, base_url=f"{FONTS_DIR.as_uri()}/").write_pdf()
    return pdf


def _install_hint(err: OSError) -> str:
    if sys.platform == "darwin":
        fix = "Install it with `brew install pango`, then restart Scribely."
    elif sys.platform == "win32":
        fix = (
            "Install the GTK3 runtime (see the WeasyPrint docs: “Installation → Windows”), "
            "then restart Scribely."
        )
    else:
        fix = "Install Pango with your package manager (e.g. `apt install libpango-1.0-0`)."
    return f"PDF export needs the Pango text library, which wasn't found ({err}). {fix}"
