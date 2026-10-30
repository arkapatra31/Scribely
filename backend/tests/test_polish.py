"""Pause/resume, audio level, speech settings, first run, search, PDF, logs and diagnostics."""

import asyncio
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import structlog

from scribely import log as logfile
from scribely.capture.base import AudioCapture, AudioChunk
from scribely.capture.dsp import TARGET_SAMPLE_RATE as SR
from scribely.config import LLMConfig, LoggingConfig, PathsConfig, Settings, SttConfig
from scribely.credentials import Credentials
from scribely.models import (
    AudioLevelMessage,
    NoteDoc,
    NoteSection,
    SearchHit,
    ServerMessage,
    Session,
    SessionNotes,
    SpeechModelMessage,
    SpeechSettings,
    SpeechSettingsMessage,
    StatusMessage,
    TranscriptSegment,
)
from scribely.session import LiveSessionManager, SessionError
from scribely.session.live import _level
from scribely.session.store import SessionStore
from scribely.stt import catalog
from scribely.stt.stream import StreamingTranscriber
from tests.stt_fakes import EnergyVAD, FakeTranscriber, LoadableFakeTranscriber, tone
from tests.test_capture_base import FakeCapture, FakeClock, collect
from tests.test_live_session import drain, file_capture, wait_idle
from tests.test_stt_stream import inline

# --- capture pause --------------------------------------------------------------------------


def test_pause_drops_audio_and_offsets_skip_the_pause() -> None:
    async def run() -> list[AudioChunk]:
        clock = FakeClock()
        cap = FakeCapture(clock=clock)
        await cap.start()
        clock.now += 1.0
        cap.push_from_thread(tone(1.0), SR)
        await asyncio.sleep(0)
        cap.pause()
        await asyncio.sleep(0)
        clock.now += 1.0
        cap.push_from_thread(tone(1.0), SR)  # dropped
        clock.now += 30.0
        cap.resume()
        clock.now += 1.0
        cap.push_from_thread(tone(1.0), SR)
        await cap.stop()
        return await collect(cap)

    chunks = asyncio.run(run())
    audio = [c for c in chunks if not c.boundary]
    boundaries = [c for c in chunks if c.boundary]
    assert len(boundaries) == 1 and len(boundaries[0].samples) == 0
    assert sum(c.duration for c in audio) == pytest.approx(2.0, abs=0.05)
    # The second stretch continues right after the first: the 31 s pause isn't in the timeline.
    assert audio[-1].start < 2.1
    order = [id(c) for c in chunks]
    assert order.index(id(boundaries[0])) > order.index(id(audio[0]))


def test_stream_finalizes_speech_at_a_pause_marker() -> None:
    async def chunks() -> Any:
        yield AudioChunk(samples=tone(1.0), start=0.0)
        yield AudioChunk(samples=np.zeros(0, dtype=np.float32), start=1.0, boundary=True)
        yield AudioChunk(samples=tone(0.5), start=1.0)

    async def run() -> list[Any]:
        stream = StreamingTranscriber(
            FakeTranscriber(),
            EnergyVAD(),
            SttConfig(partial_interval_seconds=0, speech_pad_ms=0),
            run_blocking=inline,
        )
        return [u async for u in stream.run(chunks())]

    finals = [u.text for u in asyncio.run(run()) if u.final]
    assert finals == ["speech 1.0s", "speech 0.5s"]


# --- manager: pause/resume and level ----------------------------------------------------------


def manager(
    tmp_path: Path,
    capture: AudioCapture | None = None,
    transcriber: LoadableFakeTranscriber | None = None,
) -> LiveSessionManager:
    return LiveSessionManager(
        Settings(
            stt=SttConfig(partial_interval_seconds=0),
            llm=LLMConfig(azure_endpoint="https://example.openai.azure.com/"),
            paths=PathsConfig(data_dir=tmp_path / "data"),
        ),
        store=SessionStore.open(tmp_path / "scribely.db"),
        transcriber=transcriber or LoadableFakeTranscriber(),
        capture_factory=(lambda: capture) if capture else file_capture(tmp_path),
        vad_factory=EnergyVAD,
        llm_factory=lambda cfg, key: None,  # type: ignore[arg-type,return-value]
        credentials=Credentials(),
    )


def test_pause_and_resume_change_state_and_freeze_elapsed(tmp_path: Path) -> None:
    async def run() -> tuple[list[ServerMessage], float, float]:
        cap = FakeCapture()
        m = manager(tmp_path, cap)
        queue = m.subscribe()
        await m.start()
        cap._push(tone(0.3), SR)
        await asyncio.sleep(0.15)
        await m.pause()
        assert cap.paused
        with pytest.raises(SessionError):
            await m.pause()
        frozen = m._status().elapsed
        await asyncio.sleep(0.1)
        still = m._status().elapsed
        await m.resume()
        with pytest.raises(SessionError):
            await m.resume()
        await m.pause()
        await m.stop()  # stopping while paused works
        return drain(queue), frozen, still

    messages, frozen, still = asyncio.run(run())
    states = [msg.state for msg in messages if isinstance(msg, StatusMessage)]
    assert states[-6:] == ["recording", "paused", "recording", "paused", "stopping", "idle"]
    assert frozen == still > 0
    levels = [msg.level for msg in messages if isinstance(msg, AudioLevelMessage)]
    assert levels and max(levels) > 0.5 and levels[-1] == 0.0  # pause reports silence


def test_level_scale() -> None:
    assert _level(0.0) == 0.0
    assert _level(1.0) == 1.0
    assert 0.4 < _level(0.03) < 0.6  # about -30 dBFS


# --- speech settings --------------------------------------------------------------------------


def test_speech_settings_message_lists_models_and_languages(tmp_path: Path) -> None:
    async def run() -> SpeechSettingsMessage:
        return await manager(tmp_path).speech_settings_message()

    msg = asyncio.run(run())
    assert msg.settings == SpeechSettings(model="small", language=None)
    assert [m.name for m in msg.models][:3] == ["tiny", "base", "small"]
    assert not any(m.downloaded for m in msg.models)
    assert {"code": "en", "name": "English"} in [lang.model_dump() for lang in msg.languages]


def test_save_language_applies_and_persists(tmp_path: Path) -> None:
    fake = LoadableFakeTranscriber()

    async def run() -> str | None:
        m = manager(tmp_path, transcriber=fake)
        await m.save_speech_settings(SpeechSettings(model="small", language="de"))
        assert m._model_task is not None
        await m._model_task
        await m.save_speech_settings(SpeechSettings(model="small", language="fr"))
        again = manager(tmp_path)
        await again.load_saved_speech_settings()
        return again._settings.stt.language

    assert asyncio.run(run()) == "fr"
    assert fake.configs[-1].language == "fr"
    assert fake.loads == 1  # same model: loaded once, not reloaded for a new language


def test_saving_a_new_model_loads_it_and_reports_progress(tmp_path: Path) -> None:
    fake = LoadableFakeTranscriber()

    async def run() -> list[ServerMessage]:
        m = manager(tmp_path, transcriber=fake)
        queue = m.subscribe()
        await m.save_speech_settings(SpeechSettings(model="base", language=None))
        assert m._model_task is not None
        await m._model_task
        await asyncio.sleep(0)
        return drain(queue)

    messages = asyncio.run(run())
    states = [(m.model, m.state) for m in messages if isinstance(m, SpeechModelMessage)]
    assert states == [("base", "loading"), ("base", "ready")]
    assert fake.configs[-1].model == "base" and fake.loads == 1


def test_speech_settings_are_validated(tmp_path: Path) -> None:
    async def run() -> None:
        m = manager(tmp_path, FakeCapture())
        with pytest.raises(SessionError, match="only understands English"):
            await m.save_speech_settings(SpeechSettings(model="distil-large-v3", language="de"))
        await m.start()
        with pytest.raises(SessionError, match="Stop the recording"):
            await m.save_speech_settings(SpeechSettings(model="tiny", language=None))
        await m.save_speech_settings(SpeechSettings(model="small", language="en"))  # fine
        await m.stop()

    asyncio.run(run())
    with pytest.raises(ValueError, match="Unknown language"):
        SpeechSettings(model="small", language="xx")


# --- first run ----------------------------------------------------------------------------


def test_first_run_waits_for_setup_before_loading_the_model(tmp_path: Path) -> None:
    fake = LoadableFakeTranscriber()

    async def run() -> tuple[bool, bool, bool]:
        m = manager(tmp_path, transcriber=fake)
        await m.startup()
        before = m._status().onboarded
        loading_before = m._model_task is not None
        await m.finish_onboarding()
        assert m._model_task is not None
        await m._model_task
        again = manager(tmp_path)
        await again.startup()
        return before, loading_before, again._status().onboarded

    before, loading_before, after_restart = asyncio.run(run())
    assert before is False and loading_before is False
    assert after_restart is True and fake.loads == 1


def test_existing_users_skip_setup(tmp_path: Path) -> None:
    async def run() -> bool:
        m = manager(tmp_path)
        await m.start()
        await wait_idle(m)
        again = manager(tmp_path)
        await again.startup()
        return again._status().onboarded

    assert asyncio.run(run()) is True


def test_capture_permission_off_macos(tmp_path: Path) -> None:
    async def run() -> tuple[str, str]:
        m = manager(tmp_path)
        win = await m.capture_permission("check", "win32")
        linux = await m.capture_permission("request", "linux")
        return win.state, linux.state

    assert asyncio.run(run()) == ("not_needed", "unknown")


# --- search -------------------------------------------------------------------------------


def _session(sid: str, minute: int, title: str | None = None) -> Session:
    from datetime import UTC, datetime

    return Session(
        id=sid,
        title=title,
        status="stopped",
        started_at=datetime(2026, 10, 1, 9, minute, tzinfo=UTC),
    )


def test_store_search_titles_notes_transcripts(tmp_path: Path) -> None:
    store = SessionStore.open(tmp_path / "scribely.db")
    long_text = "Intro words " * 10 + "the Krebs cycle makes ATP " + "and more words " * 10

    async def run() -> dict[str, list[SearchHit]]:
        await store.create_session(_session("a", 1, title="Krebs cycle lecture"))
        await store.create_session(_session("b", 2))
        await store.create_session(_session("c", 3))
        await store.create_session(_session("d", 4))
        for sid, text in [("b", long_text), ("c", "nothing here"), ("d", "100% sure_thing")]:
            store.queue_segment(
                TranscriptSegment(session_id=sid, index=0, start=12.0, end=14.0, text=text)
            )
        await store.flush()
        await store.save_notes(
            SessionNotes(
                session_id="c",
                doc=NoteDoc(
                    title="Respiration",
                    summary="Cells",
                    sections=[NoteSection(heading="KREBS", points=["x"], start=0, end=1)],
                ),
                provider="ollama",
                model="m",
                created_at=_session("x", 0).started_at,
            )
        )
        return {
            "krebs": await store.search("krebs"),
            "percent": await store.search("100%"),
            "underscore": await store.search("s_r"),  # "_" is literal, not a wildcard
            "blank": await store.search("   "),
            "points": await store.search("points"),  # a JSON key, not note text
        }

    found = asyncio.run(run())
    store.close()
    krebs = found["krebs"]
    assert [(h.session_id, h.field) for h in krebs] == [
        ("c", "notes"),
        ("b", "transcript"),
        ("a", "title"),
    ]
    transcript = krebs[1]
    assert transcript.start == 12.0
    assert transcript.snippet.startswith("…") and "Krebs cycle" in transcript.snippet
    assert [h.session_id for h in found["percent"]] == ["d"]
    assert found["underscore"] == [] and found["blank"] == [] and found["points"] == []


# --- PDF export, logs, diagnostics ------------------------------------------------------------


def test_export_pdf(tmp_path: Path) -> None:
    async def run() -> Path:
        m = manager(tmp_path)
        session = await m.start("Bio")
        await wait_idle(m)
        exported = await m.export_session(session.id, "pdf")
        return Path(exported.path)

    path = asyncio.run(run())
    assert path.suffix == ".pdf" and path.read_bytes().startswith(b"%PDF")


def test_pdf_text_is_escaped_and_falls_back_for_missing_glyphs() -> None:
    from scribely.export.pdf import SANS, _fonts, _FontSet

    _fonts()  # registers the bundled fonts
    no_system_fonts = _FontSet([])
    assert no_system_fonts.markup("Q&A <tags> café", SANS) == "Q&amp;A &lt;tags&gt; café"
    # CJK isn't in Inter: with no system font it uses ReportLab's built-in CJK font.
    assert no_system_fonts.markup("RAG 检索", SANS) == 'RAG <font name="STSong-Light">检索</font>'


def test_pdf_renders_any_script_without_system_libraries(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from scribely.export import render_session_pdf

    session = Session(
        id="s", title="Ελληνικά · 中文", status="stopped", started_at=datetime.now(UTC)
    )
    segments = [
        TranscriptSegment(session_id="s", index=i, start=i, end=i + 1, text=text)
        for i, text in enumerate(["Hello & <welcome>", "Привет", "검색 증강 생성", "مرحبا"])
    ]
    pdf = render_session_pdf(session, segments, None)
    assert pdf.startswith(b"%PDF") and b"/Title" in pdf


def test_log_file_and_diagnostics_never_include_keys(tmp_path: Path) -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        path = logfile.configure_logging(LoggingConfig(), tmp_path / "logs")
        assert path == tmp_path / "logs" / "scribely.log"
        structlog.get_logger("test").info("diagnostics.check", detail="hello")

        async def run() -> str:
            m = manager(tmp_path)
            m._credentials.set("azure_openai", "sk-secret-value")
            return (await m.diagnostics()).text

        text = asyncio.run(run())
    finally:
        for h in root.handlers[:]:
            root.removeHandler(h)
            h.close()
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)
        structlog.reset_defaults()
        logfile._log_file = None

    assert "diagnostics.check" in path.read_text(encoding="utf-8")
    assert "diagnostics.check" in text and "Speech model: small" in text
    assert "API key: session" in text and "sk-secret-value" not in text


# --- catalog --------------------------------------------------------------------------------


def test_catalog_download_state(tmp_path: Path) -> None:
    assert catalog.is_downloaded(str(tmp_path), tmp_path)  # a local model folder
    assert not catalog.is_downloaded("small", tmp_path)
    assert not catalog.is_downloaded("no-such-model", tmp_path)
    assert catalog.is_english_only("distil-large-v3") and catalog.is_english_only("base.en")
    assert not catalog.is_english_only("small")
    folder = tmp_path / "m"
    (folder / "blobs").mkdir(parents=True)
    (folder / "blobs" / "a.incomplete").write_bytes(b"x" * 10)
    (folder / "blobs" / "b").write_bytes(b"x" * 5)
    assert catalog._dir_bytes(folder) == 15


def test_catalog_languages_are_whisper_codes() -> None:
    from faster_whisper.tokenizer import _LANGUAGE_CODES

    assert set(catalog.LANGUAGES) <= set(_LANGUAGE_CODES)
    assert all(catalog.repo_id(m.name) for m in catalog.SPEECH_MODELS)
