# CLAUDE.md — Scribely

Context and working rules for building **Scribely**. Read this before generating or modifying code.

## What Scribely is

Scribely is a **local-first desktop app (macOS + Windows)** that listens to whatever the user is studying (any browser/video player), transcribes it live, and turns the audio into clean, structured notes after the session ends. The user stays focused on the video; Scribely takes the notes, then lets them summarize, restructure, and export to HTML.

## Non-negotiable domain rules

These shape the whole design. Do not violate them without explicit instruction.

1. **Live transcription, deferred generation.** Speech-to-text runs continuously *during* playback. The LLM (notes pipeline) runs **once, after the user stops** the session — never per-chunk during recording.
2. **Local-first & free.** Audio, transcripts, and notes stay on the user's machine. No cloud dependency, no per-minute costs, no usage caps. Cloud is an opt-in only, never the default path.
3. **Model-agnostic / config-driven.** The LLM is a config value, not a hard dependency. Never hardcode a model. Default is `gemma4:12b` on a **user-provided Ollama** instance. Validate the host + model on startup (`GET /api/tags`) and surface a clear error if the model isn't pulled.
4. **No telemetry by default.** Nothing leaves the machine unless the user explicitly opts in.
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
| Audio capture | WASAPI loopback (Windows) · ScreenCaptureKit (macOS) · `sounddevice` · VAD |
| Transcription (STT) | `faster-whisper` (CTranslate2), chunked streaming |
| Session state | SQLite (WAL mode) + in-memory rolling window for live display |
| Notes pipeline | LangGraph + `langchain-ollama` + Pydantic structured output |
| Model runtime | Ollama (user-provided), default `gemma4:12b` |
| Export | Jinja2 → HTML (WeasyPrint → PDF later) |
| Persistence | SQLite (WAL) + filesystem, via `platformdirs` |
| Config | TOML via `pydantic-settings` |
| Packaging | PyInstaller / Briefcase (Python sidecar) bundled in the Tauri app; code signing + notarization |
| Logging | `structlog` |

## Proposed repository layout

```
scribely/
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
  config.toml             # default user-editable config
  CLAUDE.md
  Plan.md
```

## Conventions

- **Schemas are the contract.** Define everything that crosses the WS boundary (transcript segments, note docs, session objects) as Pydantic models in `backend/scribely/models.py`, and **generate the TypeScript types from them** (e.g. `pydantic2ts`). Frontend never hand-writes these types.
- **Python:** type-hinted throughout; `ruff` for lint/format, `mypy` for types, `pytest` for tests. Async-first in the API and capture loops.
- **TypeScript:** strict mode on. Tailwind for styling; Framer Motion for transitions. Keep WS message handling in one typed client module.
- **Notes pipeline:** the LLM call uses `ChatOllama(model=<config>, base_url=<config>)` with `.with_structured_output(<PydanticModel>)`. Each LangGraph node is pure and re-runnable; persist a checkpoint (SQLite) so `summarize` / `restructure` can re-run without redoing `structure`.
- **Config:** read host, model, chunk size, temperature, and paths from `config.toml`. Never hardcode. Changing the model must require no code change.
- **Errors are actionable.** Surface plain-language problems ("model `gemma4:12b` not found — run `ollama pull gemma4:12b`"), not stack traces, to the UI.

## Intended commands (set up in Phase 0)

```bash
# backend (Python)
uv sync                       # or poetry install
uv run scribely-backend       # start FastAPI sidecar
pytest                        # tests
ruff check . && mypy .        # lint + types

# frontend / shell (from apps/desktop)
pnpm install
pnpm tauri dev                # run the desktop app in dev
pnpm tauri build              # produce signed installers

# regenerate TS types from Pydantic
pnpm gen:schemas
```

## Gotchas to respect

- **macOS capture** uses ScreenCaptureKit and triggers a *screen-recording* permission prompt even for audio-only. Handle the not-yet-granted state gracefully.
- **Packaging the Python sidecar inside Tauri** is the trickiest delivery step — the backend ships as a bundled binary the Rust shell launches. Plan for it early; don't assume a system Python.
- **SQLite on the live path:** use WAL mode and batched commits; keep the live UI fed from the in-memory rolling window, with SQLite as the durable source of truth.
- **Code signing/notarization** is required or the OS will block the app (Gatekeeper / SmartScreen).

## Definition of done (per component)

A component is done when it: has typed inputs/outputs, handles its failure states with actionable messages, has at least basic tests (backend) or a rendered state (UI), respects the non-negotiable domain rules above, and is wired into the WS/contract where relevant.