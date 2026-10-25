"""LangGraph notes pipeline: transcript chunks -> (map) section drafts -> (reduce) notes.

A transcript that fits the model's budget takes one call (``single``). Longer ones are
mapped chunk by chunk in parallel, then reduced; if the drafted sections are themselves too
long for one call, they are collapsed in groups first, so the context window is never
exceeded (CLAUDE.md rule 5).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict, TypeVar, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from scribely.config import Settings
from scribely.models import NoteDoc, TranscriptSegment
from scribely.pipeline import prompts
from scribely.pipeline.chunking import chunk_segments, estimate_tokens, render_chunk
from scribely.pipeline.llm_factory import LLMError, context_window, explain_error
from scribely.pipeline.schemas import DraftNotes, DraftSection, DraftSections, to_note_doc

# Room for the system prompt and instructions around each chunk.
PROMPT_OVERHEAD_TOKENS = 600
MIN_CHUNK_TOKENS = 500
MAX_COLLAPSE_ROUNDS = 5

M = TypeVar("M", bound=BaseModel)
Progress = Callable[[str], Awaitable[None]]


class NotesState(TypedDict, total=False):
    chunks: list[str]
    sections: list[DraftSection]
    notes: DraftNotes


def input_budget(settings: Settings) -> int:
    """Tokens of transcript (or drafted sections) that fit in one request."""
    window = context_window(settings.llm)
    budget = min(
        settings.pipeline.chunk_size_tokens,
        window - settings.llm.max_output_tokens - PROMPT_OVERHEAD_TOKENS,
    )
    if budget < MIN_CHUNK_TOKENS:
        raise LLMError(
            f"The model's context window ({window} tokens) is too small for notes after "
            f"reserving {settings.llm.max_output_tokens} output tokens. Lower max_output_tokens "
            "or set a larger context_window under [llm] in config.toml."
        )
    return budget


async def generate_notes(
    segments: list[TranscriptSegment],
    llm: BaseChatModel,
    settings: Settings,
    on_progress: Progress | None = None,
) -> NoteDoc:
    if not segments:
        raise LLMError("Nothing was transcribed in this session, so there's nothing to summarize.")
    budget = input_budget(settings)
    chunks = chunk_segments(segments, budget, settings.pipeline.chunk_overlap_tokens)
    graph = _build_graph(llm, settings, budget, on_progress or _no_progress)
    result = cast(NotesState, await graph.ainvoke({"chunks": [render_chunk(c) for c in chunks]}))
    return to_note_doc(result["notes"], duration=segments[-1].end)


def _build_graph(llm: BaseChatModel, settings: Settings, budget: int, progress: Progress) -> Any:
    limit = asyncio.Semaphore(settings.pipeline.max_concurrency)

    async def ask(schema: type[M], prompt: str) -> M:
        async with limit:
            try:
                runnable = llm.with_structured_output(schema)
                result = await runnable.ainvoke(
                    [SystemMessage(prompts.SYSTEM), HumanMessage(prompt)]
                )
            except Exception as err:
                raise explain_error(err, settings.llm) from err
        if not isinstance(result, schema):
            raise explain_error(ValueError("OutputParser: empty structured output"), settings.llm)
        return result

    async def single(state: NotesState) -> NotesState:
        await progress("Writing notes…")
        notes = await ask(DraftNotes, prompts.SINGLE.format(transcript=state["chunks"][0]))
        return {"notes": notes}

    async def map_chunks(state: NotesState) -> NotesState:
        chunks = state["chunks"]
        done = 0

        async def one(index: int, text: str) -> list[DraftSection]:
            nonlocal done
            drafted = await ask(
                DraftSections,
                prompts.MAP.format(index=index + 1, total=len(chunks), transcript=text),
            )
            done += 1
            await progress(f"Summarized part {done} of {len(chunks)}…")
            return drafted.sections

        await progress(f"Summarizing {len(chunks)} parts…")
        parts = await asyncio.gather(*(one(i, c) for i, c in enumerate(chunks)))
        return {"sections": [s for part in parts for s in part]}

    async def reduce(state: NotesState) -> NotesState:
        sections = state["sections"]
        for _ in range(MAX_COLLAPSE_ROUNDS):
            if _tokens(sections) <= budget:
                break
            await progress("Condensing notes…")
            groups = _group(sections, budget)
            if len(groups) == 1:  # a single group that's still too big: collapse it alone
                groups = [sections[: len(sections) // 2], sections[len(sections) // 2 :]]
            collapsed = await asyncio.gather(
                *(ask(DraftSections, prompts.COLLAPSE.format(sections=_dump(g))) for g in groups)
            )
            merged = [s for c in collapsed for s in c.sections]
            if _tokens(merged) >= _tokens(sections):
                break
            sections = merged
        if _tokens(sections) > budget:
            raise LLMError(
                "This session is too long to summarize with the configured model. Use a model "
                "with a larger context window."
            )
        await progress("Writing final notes…")
        return {"notes": await ask(DraftNotes, prompts.REDUCE.format(sections=_dump(sections)))}

    graph: StateGraph[NotesState] = StateGraph(NotesState)
    graph.add_node("single", single)
    graph.add_node("map", map_chunks)
    graph.add_node("reduce", reduce)
    graph.add_conditional_edges(
        START, lambda s: "single" if len(s["chunks"]) == 1 else "map", ["single", "map"]
    )
    graph.add_edge("map", "reduce")
    graph.add_edge("single", END)
    graph.add_edge("reduce", END)
    return graph.compile()


def _dump(sections: list[DraftSection]) -> str:
    return json.dumps([s.model_dump() for s in sections], ensure_ascii=False)


def _tokens(sections: list[DraftSection]) -> int:
    return estimate_tokens(_dump(sections))


def _group(sections: list[DraftSection], budget: int) -> list[list[DraftSection]]:
    groups: list[list[DraftSection]] = [[]]
    for s in sections:
        if groups[-1] and _tokens([*groups[-1], s]) > budget:
            groups.append([])
        groups[-1].append(s)
    return groups


async def _no_progress(_: str) -> None:
    return None
