import asyncio
from typing import Any

import httpx
import pytest

from scribely.config import LLMConfig
from scribely.pipeline import LLMError, check_llm, context_window, get_llm

KEYS = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
]


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


def test_azure_needs_endpoint_then_key(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(LLMError, match="endpoint and deployment in Settings"):
        get_llm(LLMConfig(), "key")
    cfg = LLMConfig(azure_endpoint="https://x.openai.azure.com/", azure_deployment="notes")
    with pytest.raises(LLMError, match=r"add it in Settings \(or set AZURE_OPENAI_API_KEY\)"):
        get_llm(cfg)
    llm = get_llm(cfg, "test")
    assert type(llm).__name__ == "AzureChatOpenAI"
    assert llm.deployment_name == "notes"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("provider", "env", "cls"),
    [
        ("anthropic", "ANTHROPIC_API_KEY", "ChatAnthropic"),
        ("openai", "OPENAI_API_KEY", "ChatOpenAI"),
        ("gemini", "GOOGLE_API_KEY", "ChatGoogleGenerativeAI"),
    ],
)
def test_cloud_providers_resolve_from_config(
    monkeypatch: pytest.MonkeyPatch, provider: Any, env: str, cls: str
) -> None:
    cfg = LLMConfig(provider=provider, model="some-model")
    with pytest.raises(LLMError, match=env):
        get_llm(cfg)
    assert type(get_llm(cfg, "test")).__name__ == cls


def test_ollama_needs_no_key() -> None:
    llm = get_llm(LLMConfig(provider="ollama", model="llama3.1"))
    assert type(llm).__name__ == "ChatOllama"


def test_context_windows() -> None:
    assert context_window(LLMConfig(model="gpt-4o")) == 128_000
    assert context_window(LLMConfig(provider="anthropic", model="claude-sonnet-x")) == 200_000
    assert context_window(LLMConfig(provider="ollama", model="llama3.1")) == 8_192
    assert context_window(LLMConfig(model="mystery")) == 8_192
    assert context_window(LLMConfig(model="gpt-4o", context_window=32_000)) == 32_000


def _mock_ollama(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    real = httpx.AsyncClient
    monkeypatch.setattr(
        "scribely.pipeline.llm_factory.httpx.AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


def test_ollama_check_pulled_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_ollama(
        monkeypatch, lambda req: httpx.Response(200, json={"models": [{"name": "llama3.1:latest"}]})
    )
    asyncio.run(check_llm(LLMConfig(provider="ollama", model="llama3.1")))
    with pytest.raises(LLMError, match="ollama pull gemma4:12b"):
        asyncio.run(check_llm(LLMConfig(provider="ollama", model="gemma4:12b")))


def test_ollama_check_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _mock_ollama(monkeypatch, refuse)
    with pytest.raises(LLMError, match=r"Can't reach Ollama.*ollama serve"):
        asyncio.run(check_llm(LLMConfig(provider="ollama", model="llama3.1")))
