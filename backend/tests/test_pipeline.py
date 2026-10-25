import asyncio
import os
import re
from typing import Any

import pytest
from pydantic import BaseModel

from scribely.config import LLMConfig, PipelineConfig, Settings
from scribely.models import TranscriptSegment
from scribely.pipeline import LLMError, generate_notes
from scribely.pipeline.chunking import chunk_segments, estimate_tokens, format_segment
from scribely.pipeline.graph import input_budget
from scribely.pipeline.schemas import DraftNotes, DraftSection, DraftSections
from tests.fake_llm import FakeLLM


def segments(n: int, words: int = 12) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            session_id="s",
            index=i,
            start=i * 5.0,
            end=i * 5.0 + 4.5,
            text=" ".join(f"word{i}" for _ in range(words)),
        )
        for i in range(n)
    ]


def settings(
    chunk: int = 6000, window: int | None = None, out: int = 1000, **pipe: Any
) -> Settings:
    return Settings(
        llm=LLMConfig(context_window=window, max_output_tokens=out),
        pipeline=PipelineConfig(chunk_size_tokens=chunk, chunk_overlap_tokens=50, **pipe),
    )


def section_from_prompt(prompt: str) -> DraftSection:
    stamps = [int(s) for s in re.findall(r"\[(\d+)s\]", prompt)] or [0]
    return DraftSection(
        heading=f"Part at {stamps[0]}s",
        points=["a point"],
        start_seconds=stamps[0],
        end_seconds=stamps[-1],
    )


def handler(schema: type[BaseModel], prompt: str) -> BaseModel:
    if schema is DraftSections:
        if "Combine them" in prompt:
            return DraftSections(
                sections=[
                    DraftSection(
                        heading="Merged", points=["merged"], start_seconds=0, end_seconds=1
                    )
                ]
            )
        return DraftSections(sections=[section_from_prompt(prompt)])
    assert schema is DraftNotes
    return DraftNotes(
        title="Cell respiration", summary="About cells.", sections=[section_from_prompt(prompt)]
    )


# --- chunking ------------------------------------------------------------------------------


def test_chunks_respect_budget_overlap_and_cover_everything() -> None:
    segs = segments(200)
    chunks = chunk_segments(segs, max_tokens=300, overlap_tokens=60)
    assert len(chunks) > 5
    for c in chunks:
        assert sum(estimate_tokens(format_segment(s)) + 1 for s in c) <= 300
    covered = {s.index for c in chunks for s in c}
    assert covered == set(range(200))
    assert chunks[1][0].index <= chunks[0][-1].index  # overlap carried over


def test_short_transcript_is_one_chunk() -> None:
    assert len(chunk_segments(segments(5), max_tokens=6000, overlap_tokens=200)) == 1


# --- graph ---------------------------------------------------------------------------------


def test_short_transcript_takes_one_call_and_is_cleaned() -> None:
    def h(schema: type[BaseModel], prompt: str) -> BaseModel:
        return DraftNotes(
            title=" Title ",
            summary=" Sum ",
            sections=[
                DraftSection(heading="Later", points=["b"], start_seconds=40, end_seconds=999),
                DraftSection(
                    heading="Earlier", points=["a", " "], start_seconds=-3, end_seconds=-9
                ),
                DraftSection(heading="Empty", points=[""], start_seconds=1, end_seconds=2),
            ],
        )

    llm = FakeLLM(h)
    doc = asyncio.run(generate_notes(segments(10), llm.as_chat_model(), settings()))
    assert [c[0] for c in llm.calls] == ["DraftNotes"]
    assert doc.title == "Title" and doc.summary == "Sum"
    assert [s.heading for s in doc.sections] == ["Earlier", "Later"]
    assert (
        doc.sections[0].start == 0 and doc.sections[0].end == 0 and doc.sections[0].points == ["a"]
    )
    assert doc.sections[1].end == pytest.approx(49.5)  # clamped to the transcript's end


def test_long_transcript_maps_in_parallel_then_reduces() -> None:
    llm = FakeLLM(handler, delay=0.01)
    progress: list[str] = []

    async def on_progress(msg: str) -> None:
        progress.append(msg)

    doc = asyncio.run(
        generate_notes(
            segments(300), llm.as_chat_model(), settings(chunk=800, max_concurrency=3), on_progress
        )
    )
    kinds = [c[0] for c in llm.calls]
    assert kinds.count("DraftSections") > 3 and kinds[-1] == "DraftNotes"
    assert 1 < llm.max_active <= 3
    assert "part 1 of" in llm.calls[0][1]
    assert (
        any(m.startswith("Summarized part") for m in progress)
        and progress[-1] == "Writing final notes…"
    )
    assert doc.title == "Cell respiration"


def test_too_many_sections_are_collapsed_before_reduce() -> None:
    def verbose(schema: type[BaseModel], prompt: str) -> BaseModel:
        if schema is DraftSections and "Combine them" not in prompt:
            base = section_from_prompt(prompt)
            return DraftSections(
                sections=[
                    base.model_copy(update={"points": ["detail " * 40] * 6}) for _ in range(4)
                ]
            )
        return handler(schema, prompt)

    llm = FakeLLM(verbose)
    asyncio.run(generate_notes(segments(300), llm.as_chat_model(), settings(chunk=800)))
    prompts = [p for _, p in llm.calls]
    assert any("Combine them" in p for p in prompts)
    final = prompts[-1]
    assert estimate_tokens(final) < 800 + 300


def test_provider_errors_become_plain_language() -> None:
    class AuthenticationError(Exception):
        status_code = 401

    def boom(schema: type[BaseModel], prompt: str) -> BaseModel:
        raise AuthenticationError("Incorrect API key provided: sk-…")

    with pytest.raises(LLMError, match=r"rejected the API key\. Update it in Settings"):
        asyncio.run(generate_notes(segments(5), FakeLLM(boom).as_chat_model(), settings()))


def test_tiny_context_window_is_reported() -> None:
    with pytest.raises(LLMError, match="context window \\(2000 tokens\\) is too small"):
        input_budget(settings(window=2000, out=4096))


def test_empty_transcript_is_reported() -> None:
    with pytest.raises(LLMError, match="Nothing was transcribed"):
        asyncio.run(generate_notes([], FakeLLM(handler).as_chat_model(), settings()))


def test_langsmith_tracing_is_forced_off(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    import scribely.pipeline

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    importlib.reload(scribely.pipeline)
    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
