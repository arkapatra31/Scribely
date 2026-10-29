# CLAUDE.md — Scribely

Context and working rules for building **Scribely**. Read this before generating or modifying code.

## What Scribely is

Scribely is a **local-first desktop app (macOS + Windows)** that listens to whatever the user is studying (any browser/video player), transcribes it live, and turns the audio into clean, structured notes after the session ends. The user stays focused on the video; Scribely takes the notes, then lets them summarize, restructure, and export to HTML.

## Non-negotiable domain rules

These shape the whole design. Do not violate them without explicit instruction.

1. **Live transcription, deferred generation.** Speech-to-text runs continuously *during* playback. The LLM (notes pipeline) runs **only on the user's request (e.g. Summarize) for a stopped session** — never per-chunk during recording, never automatically. Users can reopen any saved session and summarize it whenever they want.
2. **Local-first.** Audio capture, transcription (STT), transcripts, notes, and all session data stay on the user's machine — no cloud storage, no account, no per-minute STT costs. The only data that leaves the machine is the finished transcript text, sent to the user-configured LLM provider when notes are generated. Cloud providers use the user's own API keys; Ollama is the fully offline, zero-cost option.
3. **Model-agnostic / config-driven.** The LLM is a config value, not a hard dependency. Never hardcode a model or provider. Primary provider is **Azure OpenAI** (`gpt-4o` by default). Supported providers: `azure_openai`, `anthropic`, `openai`, `gemini`, `ollama`. A `llm_factory.py` module resolves the correct LangChain `Chat*` class from config — no other code changes required to switch. For Ollama, validate the host + model on startup (`GET /api/tags`) and surface a clear error if the model isn't pulled.
4. **No telemetry by default.** No usage data, analytics, or crash reports leave the machine unless the user explicitly opts in.
5. **Don't overflow context.** Read each model's context window and chunk transcripts with map-reduce so a long lecture never exceeds it.

## Locked tech stack

| Layer | Technology |
| --- | --- |
| Language (backend) | Python |
| Language (UI) | TypeScript |
| Desktop shell | Tauri (Rust) — native window, tray, auto-update |
| Frontend | React + Tailwind + Framer Motion |
| UI ↔ backend | WebSocket (live transcript + note ops) to a local FastAPI sidecar |
| Backend core | FastAPI + asyncio |
| Audio capture | WASAPI loopback via `PyAudioWPatch` (Windows) · ScreenCaptureKit via PyObjC (macOS) · `soxr` resampling to 16 kHz mono · WAV `file` backend for dev/tests |
| Transcription (STT) | `faster-whisper` (CTranslate2), chunked streaming + VAD |
| Session state | SQLite (WAL mode) + in-memory rolling window for live display |
| Notes pipeline | LangGraph + LangChain provider packages (`langchain-openai`, `langchain-anthropic`, `langchain-google-genai`, `langchain-ollama`) + Pydantic structured output |
| Model runtime | **Azure OpenAI** (default, `gpt-4o`); `anthropic` (`langchain-anthropic`), `openai`, `gemini` (`langchain-google-genai`), and Ollama (`langchain-ollama`) supported via config |
| Export | Jinja2 → HTML (WeasyPrint → PDF later) |
| Persistence | SQLite (WAL) + filesystem, via `platformdirs` |
| Config | TOML via `pydantic-settings` |
| Packaging | PyInstaller / Briefcase (Python sidecar) bundled in the Tauri app; code signing + notarization |
| Logging | `structlog` |

## Proposed repository layout

```
Scribely/                 # repo root
  apps/
    desktop/              # Tauri + React + TypeScript
      src/                # React app (components, views, ws client)
      src-tauri/          # Rust shell (window, sidecar launch, tray)
  backend/                # Python sidecar
    scribely/
      api/                # FastAPI app + WebSocket handlers
      capture/            # platform audio capture (wasapi/, screencapturekit/)
      stt/                # faster-whisper streaming wrapper + VAD
      session/            # session lifecycle, SQLite (WAL), persistence
      pipeline/           # LangGraph graph + nodes + prompts
      export/             # Jinja2 templates + HTML renderer
      models.py           # Pydantic schemas (notes, transcript, session)
      config.py           # pydantic-settings + TOML loader
    tests/
  shared/
    schemas/              # TypeScript types generated from Pydantic
  data/                   # local app data from source runs: scribely.db, models/, exports/ (gitignored)
  config.toml.example     # documented defaults; copy to config.toml at the root (gitignored)
  package.json            # pnpm workspace root (gen:schemas, dev, build)
  CLAUDE.md
```

## Conventions

- **Schemas are the contract.** Define everything that crosses the WS boundary (transcript segments, note docs, session objects) as Pydantic models in `backend/scribely/models.py`, and **generate the TypeScript types from them** (e.g. `pydantic2ts`). Frontend never hand-writes these types.
- **Python environment:** dependencies are managed only by `uv` in the isolated `backend/.venv` (`uv add`, `uv add --dev`, `uv sync`; `uv.lock` committed). Never `pip install` into the global/system Python.
- **Python:** type-hinted throughout; `ruff` for lint/format, `mypy` for types, `pytest` for tests. Async-first in the API and capture loops.
- **TypeScript:** strict mode on. Tailwind for styling; Framer Motion for transitions. Keep WS message handling in one typed client module.
- **Notes pipeline:** the LLM call uses `llm_factory.get_llm(cfg)` which returns the appropriate `Chat*` instance (e.g. `AzureChatOpenAI`, `ChatAnthropic`, `ChatOpenAI`, `ChatGoogleGenerativeAI`, `ChatOllama`) based on `config.toml`. All nodes call `.with_structured_output(<PydanticModel>)` — this API is identical across providers. Each LangGraph node is pure and re-runnable; persist a checkpoint (SQLite) so `summarize` / `restructure` can re-run without redoing `structure`.
- **Project-local data:** when running from a source checkout, everything lives inside the repo: `config.toml` at the root and `data/` (database, Whisper models, exports). Packaged builds use the per-user folders from `platformdirs`. Relative `[paths]` values resolve against the project root.
- **Config:** read host, model, chunk size, temperature, and paths from `config.toml` (precedence: defaults < `config.toml` < `SCRIBELY_<SECTION>__<KEY>` env vars). The notes LLM (provider, model, Azure endpoint/deployment, Ollama host) and the speech model + language can also be set in the app (Settings, first-run setup), which is saved in SQLite and overrides `config.toml`. Never hardcode. Changing the model must require no code change.
- **Logs stay local.** structlog writes to the console and a rotating `data/logs/scribely.log`. Never log API keys or transcript/notes text; the diagnostics report (Settings → Help) follows the same rule.
- **API keys are never stored.** Not in config, the database, the OS keychain, or logs. The user enters the key in Settings each time Scribely starts; it lives only in the backend's memory (`scribely/credentials.py`). The provider's standard env var (e.g. `AZURE_OPENAI_API_KEY`) is accepted as a fallback. Never send a key back to the UI.
- **Errors are actionable.** Surface plain-language problems ("model `gemma4:12b` not found — run `ollama pull gemma4:12b`"), not stack traces, to the UI.

## Git workflow

- **Never commit directly to `main`.** All work goes on a feature branch, which is merged into `main` via pull request.
- **Branch naming:** `<type>/<short-kebab-case-description>`. Types: `feature`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`. Examples: `feature/wasapi-capture`, `fix/ws-reconnect`, `docs/multi-provider-llm`.
- One branch per logical change; keep branches short-lived.

## Commands

```bash
# backend (Python) — run from backend/; uv manages the isolated backend/.venv
uv sync                                   # create/update .venv from uv.lock
uv run scribely-backend                   # start FastAPI sidecar (127.0.0.1:8765)
uv run scribely-capture-check            # record 10 s of system audio to capture-check.wav
uv run scribely-transcribe-check         # live-transcribe system audio in the terminal
uv run pytest                             # tests
uv run ruff check . && uv run ruff format --check . && uv run mypy .   # lint + format + types

# workspace (TypeScript + Tauri) — run from repo root
pnpm install
pnpm gen:schemas                          # regenerate shared/schemas/models.ts from Pydantic
pnpm typecheck                            # gen:schemas + tsc across workspace
pnpm dev                                  # pnpm tauri dev; the app starts the backend itself (reuses one already on :8765)
pnpm build                                # pnpm tauri build (installers)
# PDF export needs Pango: brew install pango (macOS). CI (.github/workflows/ci.yml) runs the
# backend checks on macOS/Windows/Linux, the frontend build, and cargo fmt/clippy/test.
```

## Gotchas to respect

- **macOS capture** uses ScreenCaptureKit and triggers a *screen-recording* permission prompt even for audio-only. Handle the not-yet-granted state gracefully.
- **Packaging the Python sidecar inside Tauri** is the trickiest delivery step — the backend ships as a bundled binary the Rust shell launches. Plan for it early; don't assume a system Python.
- **SQLite on the live path:** use WAL mode and batched commits; keep the live UI fed from the in-memory rolling window, with SQLite as the durable source of truth.
- **Code signing/notarization** is required or the OS will block the app (Gatekeeper / SmartScreen).

## Definition of done (per component)

A component is done when it: has typed inputs/outputs, handles its failure states with actionable messages, has at least basic tests (backend) or a rendered state (UI), respects the non-negotiable domain rules above, and is wired into the WS/contract where relevant.