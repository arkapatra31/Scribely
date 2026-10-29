"""Restructure: rewrite existing notes in another style without re-reading the transcript."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from scribely.config import Settings
from scribely.models import NoteDoc, RestructureStyle
from scribely.pipeline import prompts
from scribely.pipeline.chunking import estimate_tokens
from scribely.pipeline.graph import input_budget
from scribely.pipeline.llm_factory import LLMError, explain_error
from scribely.pipeline.schemas import DraftNotes, to_note_doc


async def restructure_notes(
    doc: NoteDoc, style: RestructureStyle, llm: BaseChatModel, settings: Settings
) -> NoteDoc:
    notes_json = doc.model_dump_json()
    if estimate_tokens(notes_json) > input_budget(settings):
        raise LLMError(
            "These notes are too long to restructure with the configured model. Use a model with "
            "a larger context window."
        )
    prompt = prompts.RESTRUCTURE[style] + prompts.RESTRUCTURE_SUFFIX.format(notes=notes_json)
    try:
        result = await llm.with_structured_output(DraftNotes).ainvoke(
            [SystemMessage(prompts.SYSTEM), HumanMessage(prompt)]
        )
    except Exception as err:
        raise explain_error(err, settings.llm) from err
    if not isinstance(result, DraftNotes):
        raise explain_error(ValueError("OutputParser: empty structured output"), settings.llm)
    duration = max((s.end for s in doc.sections), default=0.0)
    return to_note_doc(result, duration)
