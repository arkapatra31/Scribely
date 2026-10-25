"""Resolve the configured LangChain chat model. The only module that knows providers."""

from __future__ import annotations

import os
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel

from scribely.config import LLMConfig

_KEY_ENV = {
    "azure_openai": "AZURE_OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}

_PROVIDER_NAMES = {
    "azure_openai": "Azure OpenAI",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "ollama": "Ollama",
}

# Context windows (tokens) by model-name prefix, longest prefix first. Used to size transcript
# chunks; [llm] context_window overrides it.
_CONTEXT_WINDOWS: list[tuple[str, int]] = [
    ("gpt-4o", 128_000),
    ("gpt-4.1", 1_000_000),
    ("gpt-5", 400_000),
    ("o3", 200_000),
    ("o4", 200_000),
    ("claude", 200_000),
    ("gemini-1.5", 1_000_000),
    ("gemini-2", 1_000_000),
    ("gemini", 128_000),
]
_DEFAULT_CONTEXT_WINDOW = 8_192  # conservative for unknown and local (Ollama) models


class LLMError(Exception):
    """LLM setup or request problem with a plain-language message safe to show the user."""


def provider_name(cfg: LLMConfig) -> str:
    return _PROVIDER_NAMES[cfg.provider]


def context_window(cfg: LLMConfig) -> int:
    if cfg.context_window is not None:
        return cfg.context_window
    if cfg.provider == "ollama":
        return _DEFAULT_CONTEXT_WINDOW
    name = cfg.model.lower()
    for prefix, size in sorted(_CONTEXT_WINDOWS, key=lambda p: -len(p[0])):
        if name.startswith(prefix):
            return size
    return _DEFAULT_CONTEXT_WINDOW


def _azure_endpoint(cfg: LLMConfig) -> str | None:
    return cfg.azure_endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")


def get_llm(cfg: LLMConfig) -> BaseChatModel:
    """Build the chat model for ``cfg``; raises LLMError if required settings are missing."""
    _check_settings(cfg)
    common: dict[str, Any] = {"temperature": cfg.temperature, "max_retries": 2}
    match cfg.provider:
        case "azure_openai":
            from langchain_openai import AzureChatOpenAI

            return AzureChatOpenAI(
                azure_endpoint=_azure_endpoint(cfg),
                azure_deployment=cfg.azure_deployment or cfg.model,
                api_version=cfg.azure_api_version,
                model=cfg.model,
                max_tokens=cfg.max_output_tokens,
                timeout=cfg.request_timeout_seconds,
                **common,
            )
        case "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=cfg.model,
                max_tokens=cfg.max_output_tokens,
                timeout=cfg.request_timeout_seconds,
                **common,
            )
        case "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=cfg.model,
                max_tokens=cfg.max_output_tokens,
                default_request_timeout=cfg.request_timeout_seconds,
                **common,
            )
        case "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=cfg.model,
                max_output_tokens=cfg.max_output_tokens,
                timeout=cfg.request_timeout_seconds,
                **common,
            )
        case "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=cfg.model,
                base_url=cfg.ollama_host,
                temperature=cfg.temperature,
                num_ctx=context_window(cfg),
                num_predict=cfg.max_output_tokens,
            )


def _check_settings(cfg: LLMConfig) -> None:
    name = provider_name(cfg)
    if cfg.provider == "azure_openai" and not _azure_endpoint(cfg):
        raise LLMError(
            "Azure OpenAI isn't set up: add azure_endpoint (and azure_deployment) under [llm] "
            "in config.toml, or set the AZURE_OPENAI_ENDPOINT environment variable."
        )
    env = _KEY_ENV.get(cfg.provider)
    if env and not os.environ.get(env):
        raise LLMError(
            f"No API key for {name}: set the {env} environment variable before starting "
            "Scribely. Keys are never stored in config.toml."
        )


async def check_llm(cfg: LLMConfig) -> None:
    """Validate settings without spending tokens; for Ollama, confirm the model is pulled."""
    _check_settings(cfg)
    if cfg.provider != "ollama":
        return
    url = cfg.ollama_host.rstrip("/") + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            names = {m.get("name", "") for m in resp.json().get("models", [])}
    except (httpx.HTTPError, ValueError) as err:
        raise LLMError(
            f"Can't reach Ollama at {cfg.ollama_host} ({err.__class__.__name__}). Start it with "
            "`ollama serve`, or fix ollama_host under [llm] in config.toml."
        ) from None
    wanted = cfg.model if ":" in cfg.model else f"{cfg.model}:latest"
    if cfg.model not in names and wanted not in names:
        raise LLMError(
            f'Model "{cfg.model}" isn\'t pulled in Ollama. Run `ollama pull {cfg.model}`.'
        )


def explain_error(err: Exception, cfg: LLMConfig) -> LLMError:
    """Turn a provider SDK exception into a plain-language LLMError."""
    if isinstance(err, LLMError):
        return err
    name = provider_name(cfg)
    kind = type(err).__name__
    status = getattr(err, "status_code", None) or getattr(
        getattr(err, "response", None), "status_code", None
    )
    if "Authentication" in kind or status in (401, 403):
        env = _KEY_ENV.get(cfg.provider, "API key")
        return LLMError(f"{name} rejected the API key. Check the {env} environment variable.")
    if "NotFound" in kind or status == 404:
        what = "deployment" if cfg.provider == "azure_openai" else "model"
        target = cfg.azure_deployment or cfg.model if cfg.provider == "azure_openai" else cfg.model
        return LLMError(f'{name} couldn\'t find the {what} "{target}". Check [llm] in config.toml.')
    if "RateLimit" in kind or status == 429:
        return LLMError(
            f"{name} is rate-limiting requests or the quota is used up. Try again later."
        )
    if "Timeout" in kind:
        return LLMError(
            f"{name} took too long to answer. Try again, or raise request_timeout_seconds."
        )
    if "Connection" in kind or isinstance(err, httpx.ConnectError):
        return LLMError(
            f"Couldn't reach {name}. Check your internet connection (or that Ollama is running)."
        )
    if "OutputParser" in kind or "ValidationError" in kind:
        return LLMError(
            f"{name} returned notes in an unexpected format. Try again, or use a more "
            "capable model."
        )
    return LLMError(f"{name} request failed: {err}")
