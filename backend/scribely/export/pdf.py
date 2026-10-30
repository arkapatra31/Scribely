"""PDF export with ReportLab, styled like the app's Notes view.

Pure pip dependency (no system libraries): fonts are the app's Inter and Newsreader, bundled
as static TTFs. Characters those fonts lack (Greek, Cyrillic, CJK, ...) fall back to a
Unicode font found on the system, or to ReportLab's built-in CJK fonts.
"""

from __future__ import annotations

import functools
import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from scribely import __version__
from scribely.export.html import _PROVIDERS, _STYLES, clock, session_title
from scribely.models import Session, SessionNotes, TranscriptSegment

FONTS_DIR = Path(__file__).parent / "fonts"

# The app's light theme (apps/desktop/src/index.css).
PAPER = HexColor("#faf8f4")
INK = HexColor("#1d1c1a")
MUTED = HexColor("#6b665e")
FAINT = HexColor("#a39d93")
LINE = HexColor("#e6e1d7")
ACCENT = HexColor("#4f46e5")
ACCENT_INK = HexColor("#3730a3")
ACCENT_SOFT = HexColor("#eef0ff")
SUMMARY_BG = HexColor("#f3f3fd")
SUMMARY_LINE = HexColor("#dedcf7")
DOT = HexColor("#958fef")

SANS, SANS_MEDIUM, SANS_BOLD = "Inter", "Inter-Medium", "Inter-SemiBold"
SERIF, SERIF_BOLD = "Newsreader", "Newsreader-SemiBold"
MONO = "Courier"

MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 20 * mm, 22 * mm, 22 * mm
NUM_COL = 26  # points; the "01" column beside each section

# System TrueType fonts for characters Inter/Newsreader lack, tried in order and loaded only
# when needed (path, index inside a .ttc collection). ReportLab embeds TrueType (glyf) fonts
# only, so CFF-based .otf fonts can't be used.
_FALLBACKS: dict[str, list[tuple[str, int]]] = {
    "darwin": [
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0),  # CJK, Greek, Arabic, Indic...
        ("/Library/Fonts/Arial Unicode.ttf", 0),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
    ],
    "win32": [
        ("C:/Windows/Fonts/segoeui.ttf", 0),  # Latin, Greek, Cyrillic, Hebrew, Arabic
        ("C:/Windows/Fonts/msyh.ttc", 0),  # Chinese
        ("C:/Windows/Fonts/YuGothR.ttc", 0),  # Japanese
        ("C:/Windows/Fonts/malgun.ttf", 0),  # Korean
        ("C:/Windows/Fonts/Nirmala.ttf", 0),  # Indic
        ("C:/Windows/Fonts/LeelawUI.ttf", 0),  # Thai
        ("C:/Windows/Fonts/arialuni.ttf", 0),
    ],
    "linux": [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
        ("/usr/share/fonts/TTF/DejaVuSans.ttf", 0),
    ],
}


@functools.cache
def _fonts() -> _FontSet:
    for name, file in [
        (SANS, "Inter-Regular.ttf"),
        (SANS_MEDIUM, "Inter-Medium.ttf"),
        (SANS_BOLD, "Inter-SemiBold.ttf"),
        (SERIF, "Newsreader-Regular.ttf"),
        (SERIF_BOLD, "Newsreader-SemiBold.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, FONTS_DIR / file))
    return _FontSet(_FALLBACKS.get(sys.platform, []))


class _FontSet:
    """Wraps runs of characters the bundled fonts can't draw in a font that can."""

    def __init__(self, candidates: list[tuple[str, int]]) -> None:
        self._candidates = [c for c in candidates if Path(c[0]).is_file()]
        self._loaded: list[str] = []
        self._covered: dict[str, set[int]] = {}
        self._choice: dict[str, str | None] = {}

    def covers(self, font: str, char: str) -> bool:
        if font not in self._covered:
            face = pdfmetrics.getFont(font).face  # type: ignore[attr-defined]
            self._covered[font] = set(face.charToGlyph)
        return ord(char) in self._covered[font]

    def markup(self, text: str, font: str) -> str:
        """XML-escaped ``text`` for a Paragraph whose base font is ``font``."""
        out: list[str] = []
        run, run_font = "", font
        for ch in text:
            want = font if ch.isspace() or self.covers(font, ch) else self._fallback(ch) or font
            if want != run_font and run:
                out.append(_wrap(run, run_font, font))
                run = ""
            run_font = want
            run += ch
        if run:
            out.append(_wrap(run, run_font, font))
        return "".join(out)

    def _fallback(self, ch: str) -> str | None:
        if ch in self._choice:
            return self._choice[ch]
        found = next((f for f in self._loaded if self.covers(f, ch)), None)
        while found is None and self._candidates:
            path, index = self._candidates.pop(0)
            name = f"Fallback{len(self._loaded)}"
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
            except Exception:  # e.g. a CFF-based font ReportLab can't embed
                continue
            self._loaded.append(name)
            if self.covers(name, ch):
                found = name
        if found is None:
            found = _cid_for(ch)  # last resort: viewer-provided CJK fonts (not embedded)
        self._choice[ch] = found
        return found


def _wrap(run: str, run_font: str, base: str) -> str:
    text = escape(run)
    return text if run_font == base else f'<font name="{run_font}">{text}</font>'


def _cid_for(ch: str) -> str | None:
    cp = ord(ch)
    if 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F or 0xAC00 <= cp <= 0xD7AF:
        return _cid("HYGothic-Medium")
    if 0x3040 <= cp <= 0x30FF:
        return _cid("HeiseiKakuGo-W5")
    if 0x2E80 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF or 0xFF00 <= cp <= 0xFFEF:
        return _cid("STSong-Light")
    return None


@functools.cache
def _cid(name: str) -> str:
    pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def _style(name: str, font: str, size: float, leading: float, color: Any, **kw: Any) -> Any:
    return ParagraphStyle(
        name, fontName=font, fontSize=size, leading=leading, textColor=color, **kw
    )


class _Styles:
    brand = _style("brand", SANS_BOLD, 8, 10, ACCENT, spaceAfter=16)
    h1 = _style("h1", SERIF_BOLD, 24, 29, INK, spaceAfter=6)
    meta = _style("meta", SANS, 9, 13, MUTED)
    label = _style("label", SANS_BOLD, 7.5, 10, ACCENT_INK, spaceAfter=3)
    summary = _style("summary", SERIF, 12, 18, INK)
    num = _style("num", MONO, 8.5, 18, FAINT)
    heading = _style("heading", SERIF_BOLD, 14, 18, INK)
    pill = _style("pill", MONO, 7.5, 9, MUTED, alignment=1)
    tag = _style("tag", SANS_MEDIUM, 8, 10, ACCENT_INK, alignment=1)
    point = _style(
        "point", SANS, 10.5, 16, INK,
        leftIndent=14, bulletIndent=1, bulletFontName=SANS_BOLD, bulletFontSize=11,
        bulletColor=DOT, spaceBefore=3,
    )  # fmt: skip
    transcript_head = _style("thead", SERIF_BOLD, 14, 18, INK, spaceAfter=8)
    line = _style(
        "line", SANS, 10, 15, INK,
        leftIndent=44, bulletIndent=0, bulletFontName=MONO, bulletFontSize=7.5,
        bulletColor=FAINT, spaceBefore=2.5,
    )  # fmt: skip
    footer = _style("footer", SANS, 8, 11, FAINT)


def render_session_pdf(
    session: Session, segments: list[TranscriptSegment], notes: SessionNotes | None
) -> bytes:
    fonts = _fonts()
    st = _Styles
    title = notes.doc.title if notes else session_title(session)
    started = session.started_at.astimezone()
    duration = clock(segments[-1].end if segments else 0.0)
    width = A4[0] - 2 * MARGIN_X
    t = fonts.markup

    story: list[Flowable] = [
        Paragraph("SCRIBELY", st.brand),
        Paragraph(t(title, SERIF_BOLD), st.h1),
    ]
    meta = [session_title(session)] if notes else []
    meta += [f"{started:%A, %d %B %Y · %H:%M}", duration]
    meta_para = Paragraph(
        '  <font color="#a39d93">·</font>  '.join(t(m, SANS) for m in meta), st.meta
    )
    style_label = _STYLES.get(notes.style, "") if notes else ""
    if style_label:
        tag = _pill(style_label, st.tag, ACCENT_SOFT, None, SANS_MEDIUM, 8, pad=7)
        story.append(_row([meta_para, tag], width))
    else:
        story.append(meta_para)

    if notes:
        story.append(Spacer(1, 18))
        story.append(_summary_card(t(notes.doc.summary, SERIF), width))
        for i, section in enumerate(notes.doc.sections, 1):
            first = next((s for s in segments if s.end >= section.start), None)
            time_text = f"{clock(section.start)} \u2013 {clock(section.end)}"
            link = f'<a href="#t{first.index}">{time_text}</a>' if first else time_text
            pill = _pill(link, st.pill, None, LINE, MONO, 7.5, pad=6, text_for_width=time_text)
            heading = Paragraph(t(section.heading, SERIF_BOLD), st.heading)
            head = _row([heading, pill], width - NUM_COL, font=SERIF_BOLD, size=14)
            body: list[Flowable] = [head]
            body += [Paragraph(t(p, SANS), st.point, bulletText="•") for p in section.points]
            table = Table(
                [[Paragraph(f"{i:02d}", st.num), body]], colWidths=[NUM_COL, width - NUM_COL]
            )
            table.setStyle(_tight([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story += [Spacer(1, 16), KeepTogether([table])]
        provider = _PROVIDERS.get(notes.provider, notes.provider)
        edited = " · edited by you" if notes.edited else ""
        story += [
            Spacer(1, 26),
            _Rule(width),
            Spacer(1, 8),
            Paragraph(
                f"Written by {escape(provider)} · {escape(notes.model)}{edited} · "
                f"Exported from Scribely on {datetime.now().astimezone():%d %B %Y, %H:%M}",
                st.footer,
            ),
        ]

    if segments:
        story += [PageBreak()] if notes else [Spacer(1, 26), _Rule(width), Spacer(1, 12)]
        story.append(Paragraph("Full transcript", st.transcript_head))
        for s in segments:
            story.append(
                Paragraph(
                    f'<a name="t{s.index}"/>{t(s.text, SANS)}', st.line, bulletText=clock(s.start)
                )
            )
    if not notes:
        story += [
            Spacer(1, 24),
            Paragraph(
                f"Exported from Scribely on {datetime.now().astimezone():%d %B %Y, %H:%M}",
                st.footer,
            ),
        ]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=title,
        author="Scribely",
        creator=f"Scribely {__version__}",
    )
    doc.build(
        story,
        onFirstPage=_paper,
        onLaterPages=_paper,
        canvasmaker=_canvas_maker(fonts.markup(title, SANS)),
    )
    return buf.getvalue()


# --- building blocks ---------------------------------------------------------------------


def _tight(extra: list[tuple[Any, ...]] | None = None) -> TableStyle:
    cmds: list[tuple[Any, ...]] = [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]
    return TableStyle(cmds + (extra or []))


def _pill(
    markup: str,
    style: Any,
    fill: Any,
    stroke: Any,
    font: str,
    size: float,
    *,
    pad: float,
    text_for_width: str | None = None,
) -> Table:
    """A rounded label sized to its text (time chips, the style tag)."""
    w = pdfmetrics.stringWidth(text_for_width or markup, font, size) + 2 * pad + 1
    cmds: list[tuple[Any, ...]] = [
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]
    if fill is not None:
        cmds.append(("BACKGROUND", (0, 0), (-1, -1), fill))
    if stroke is not None:
        cmds.append(("BOX", (0, 0), (-1, -1), 0.75, stroke))
    table = Table([[Paragraph(markup, style)]], colWidths=[w])
    table.setStyle(TableStyle(cmds))
    return table


def _row(cells: list[Flowable], width: float, *, font: str = SANS, size: float = 9) -> Table:
    """A paragraph followed by a pill on the same line; the paragraph wraps if it's long."""
    first, pill = cells
    assert isinstance(first, Paragraph) and isinstance(pill, Table)
    pill_w = pill._colWidths[0]  # type: ignore[attr-defined]
    natural = pdfmetrics.stringWidth(first.getPlainText(), font, size) + 6
    first_w = min(natural, width - pill_w - 10)
    table = Table(
        [[first, pill, ""]], colWidths=[first_w, pill_w + 10, width - first_w - pill_w - 10]
    )
    table.hAlign = "LEFT"
    table.setStyle(
        _tight(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (1, 0), (1, 0), 8),
                # line the chip up with the first line of text
                ("TOPPADDING", (1, 0), (1, 0), max(0.0, (first.style.leading - 12.5) / 2)),
            ]
        )
    )
    return table


def _summary_card(markup: str, width: float) -> Table:
    label = _fonts().markup("✦", SANS_BOLD) + "  SUMMARY"
    card = Table(
        [[[Paragraph(label, _Styles.label), Paragraph(markup, _Styles.summary)]]],
        colWidths=[width],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SUMMARY_BG),
                ("BOX", (0, 0), (-1, -1), 0.75, SUMMARY_LINE),
                ("ROUNDEDCORNERS", [12, 12, 12, 12]),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("TOPPADDING", (0, 0), (-1, -1), 13),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
            ]
        )
    )
    return card


class _Rule(Flowable):
    def __init__(self, width: float) -> None:
        super().__init__()
        self.width, self.height = width, 1

    def draw(self) -> None:
        self.canv.setStrokeColor(LINE)
        self.canv.setLineWidth(0.75)
        self.canv.line(0, 0, self.width, 0)


def _paper(canvas: Canvas, _doc: Any) -> None:
    """Runs before each page's content: the app's warm paper colour."""
    w, h = A4
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, w, h, stroke=0, fill=1)
    canvas.restoreState()


def _canvas_maker(title_markup: str) -> type[Canvas]:
    """A canvas that adds the footer (title, and "n / N" once the page count is known)."""

    class PageCanvas(Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._pages: list[dict[str, Any]] = []

        def showPage(self) -> None:
            # Keep each page's state; pages are drawn in save(), once the total is known.
            self._pages.append(dict(self.__dict__))
            self._startPage()  # type: ignore[attr-defined]

        def save(self) -> None:
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total: int) -> None:
            page = self.getPageNumber()
            w, _h = A4
            self.saveState()
            self.setFont(SANS, 8)
            self.setFillColor(FAINT)
            self.drawRightString(w - MARGIN_X, 12 * mm, f"{page} / {total}")
            if page > 1:
                footer = Paragraph(title_markup, _Styles.footer)
                footer.wrapOn(self, w - 2 * MARGIN_X - 40, 20)
                footer.drawOn(self, MARGIN_X, 12 * mm - 2)
            self.restoreState()

    return PageCanvas
