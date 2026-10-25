"""Notes pipeline: transcript -> structured notes via a configurable LLM (LangGraph)."""

import os

# No telemetry (CLAUDE.md rule 4): never let LangChain/LangSmith tracing ship transcripts
# off the machine, even if the user's shell enables it for other projects.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from scribely.pipeline.graph import generate_notes
from scribely.pipeline.llm_factory import LLMError, check_llm, context_window, get_llm

__all__ = ["LLMError", "check_llm", "context_window", "generate_notes", "get_llm"]
