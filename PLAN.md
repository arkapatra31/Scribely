# PLAN.md — Scribely Build Map

A component-by-component plan for building Scribely. Phases are ordered so a **working end-to-end slice exists as early as possible** (Phase 5), then capabilities are layered on. Each component lists its goal, deliverable, what it depends on, and how you know it's done.

Legend: **D** = depends on · **DoD** = done when.

---

## Phase 0 · Foundation & scaffolding

Set up the skeleton both languages live in before any feature work.

- **0.1 Repo & tooling** — monorepo layout (`apps/desktop`, `backend`, `shared`), Python env (`uv`/`poetry`, `ruff`, `mypy`, `pytest`), TS env (Tauri + React + Tailwind + strict TS), `pnpm` scripts.
  - DoD: `pnpm tauri dev` opens an empty window; `uv run scribely-backend` starts an empty FastAPI app on localhost.
- **0.2 Config system** — `config.toml` + `pydantic-settings` loader (LLM provider + model, Ollama host, chunk size, temperature, paths via `platformdirs`). Provider API keys come from environment variables, never from committed config.
  - DoD: backend boots reading config; bad/missing values produce clear errors.
- **0.3 Shared schemas** — Pydantic models in `models.py` for `TranscriptSegment`, `Session`, `NoteSection`, `NoteDoc`; TS type generation wired (`pnpm gen:schemas`).
  - DoD: editing a Pydantic model regenerates matching TS types.

---

## Phase 1 · Audio capture

The hardest, most platform-specific piece — de-risk it early.

- **1.1 Windows capture** — WASAPI loopback (`PyAudioWPatch`) → PCM stream.
- **1.2 macOS capture** — ScreenCaptureKit audio-only → PCM stream; handle the screen-recording permission prompt + not-granted state.
- **1.3 Unified capture interface** — one async Python API (`start()/stop()/stream()`) over both backends plus a WAV `file` backend for dev/tests; output is 16 kHz mono float32 chunks with wall-clock-aligned offsets (loopback sources go quiet during silence). `scribely-capture-check` records to WAV for hardware verification.
  - D: 0.1 · DoD: on both OSes, playing audio in any browser yields a continuous PCM stream into the backend; permission denial is handled gracefully.

---

## Phase 2 · Live transcription (STT)

- **2.1 faster-whisper wrapper** — load model, transcribe chunked audio with timestamps; VAD segmentation (Silero, bundled with faster-whisper) to cut the stream at speech pauses.
- **2.2 Streaming loop** — feed capture chunks → rolling, timestamped transcript; final segments at VAD pauses (or cut at the longest pause after `max_segment_seconds`), plus live partial hypotheses that back off when the CPU can't keep up. `scribely-transcribe-check` prints the live transcript in a terminal.
  - D: 1.3 · DoD: speaking into a captured source produces timestamped transcript text within ~1–2s, continuously.

---

> **Build-order change:** a thin live slice (4.2 WebSocket + 5.2 live transcript view, with an in-memory session manager) was built before Phase 3 so the app is usable end to end early. Phase 3 persistence plugs into that session manager.

## Phase 3 · Session state & persistence

- **3.1 SQLite (WAL)** — schema for sessions, transcript segments, notes, checkpoints; `platformdirs` location.
- **3.2 Session lifecycle** — start/stop, in-memory rolling window for live display, batched durable writes; crash-safe + resumable.
  - D: 0.2, 2.2 · DoD: a recording survives an app kill mid-session and reloads from SQLite.
- **3.3 Session list** — sidebar of saved sessions; open any past session's transcript (also while recording), rename, delete. Sessions cut off by a crash reappear as *interrupted* with their saved segments. ✅

---

## Phase 4 · Backend core & live transport

- **4.1 FastAPI sidecar** — process lifecycle, health, startup validation of the configured LLM provider (credentials present for `azure_openai` / `anthropic` / `openai` / `gemini`; host + model via `/api/tags` for `ollama`).
- **4.2 WebSocket** — push live transcript segments to the client; accept control messages (start/stop, note ops). ✅ `/ws` with start/stop, status, partial/final segments, errors; Origin allowlist.
  - D: 2.2, 3.2 · DoD: a WS client receives transcript segments in real time and can start/stop a session.

---

## Phase 5 · Desktop shell + live UI  ← first end-to-end slice

- **5.1 Tauri shell** — native window, tray, and **launching/supervising the Python sidecar**.
- **5.2 Live transcript view** — typed WS client; record/pause/stop controls; streaming transcript; recording indicator + timer. ✅ record/stop (pause later), live partials, offline/error banners.
  - D: 4.2 · DoD: **vertical slice works** — open app → record → watch live transcript stream from real captured audio → stop. (No notes yet.)

---

## Phase 6 · Notes pipeline (GenAI)

- **6.0 LLM factory** — `llm_factory.get_llm(cfg)` resolves `AzureChatOpenAI` (default, `gpt-4o`), `ChatAnthropic`, `ChatOpenAI`, `ChatGoogleGenerativeAI`, or `ChatOllama` from `config.toml`, plus the model's context window for chunking.
  - D: 0.2 · DoD: switching provider/model is a config-only change; a misconfigured provider yields a plain-language error.
- **6.1 LangGraph graph** — state + nodes: `structure` → (`summarize` | `restructure`) → `export`; SQLite checkpointer.
- **6.2 Structure node** — `get_llm(cfg).with_structured_output(NoteDoc)`; map-reduce chunking sized to the model's context window; timestamps preserved.
- **6.3 Summarize / restructure nodes** — re-runnable on existing notes without redoing structure.
  - D: 3.1, 4.1, 6.0 · DoD: a finished transcript yields a validated `NoteDoc`; summarize/restructure run independently and cheaply.

---

## Phase 7 · Notes UI

- **7.1 Notes viewer** — render `NoteDoc` sections + timestamp chips that jump back to the video moment.
- **7.2 Actions** — Summarize / Restructure / Export buttons wired to the pipeline over WS; quiet toasts, loading states. Available on any stopped session opened from the list — summarizing is on demand, never automatic.
- **7.3 Editor** — light inline editing of generated notes.
  - D: 5.2, 6.3 · DoD: stop a session → notes appear → user can summarize, restructure, and edit.

---

## Phase 8 · Export

- **8.1 HTML export** — Jinja2 template → beautified, standalone, shareable HTML with working timestamp links.
- **8.2 (Later) PDF** — WeasyPrint.
  - D: 7.1 · DoD: Export produces a self-contained HTML file that opens cleanly in any browser.

---

## Phase 9 · Settings & configuration UI

- **9.1 Settings panel** — edit LLM provider, model, credentials, Ollama host, chunk size, theme; live validation (credential check for cloud providers, `/api/tags` for Ollama).
- **9.2 Empty/onboarding states** — first-run guidance (pick a provider — Azure OpenAI default, or Anthropic / OpenAI / Gemini / Ollama — pick a model, grant mac permission).
  - D: 4.1, 5.1 · DoD: a new user can configure provider + model and start their first session without touching files.

---

## Phase 10 · Cross-cutting & polish

- **10.1 Theming** — ship the chosen direction (Scribely visual identity); light/dark + warm night mode; reduced-motion.
- **10.2 Observability** — `structlog` logging, actionable error surfacing throughout.
- **10.3 UX calm pass** — focus mode, gentle motion, comfortable reading column, inviting empty states.
  - D: most prior phases · DoD: the app feels finished and calm; errors are plain-language.

---

## Phase 11 · Packaging & distribution

- **11.1 Bundle sidecar** — PyInstaller/Briefcase the Python backend into a binary the Tauri shell launches.
- **11.2 Installers** — `pnpm tauri build` for macOS + Windows.
- **11.3 Signing** — macOS notarization, Windows code signing.
- **11.4 Auto-update** — Tauri updater channel.
  - D: 5.1 + feature-complete app · DoD: a signed installer runs on a clean machine (with the user's own provider key or local Ollama) end to end.

---

## Build order rationale

1. **Phases 0–4** build the risky, invisible plumbing (capture, STT, persistence, transport).
2. **Phase 5** stitches them into a working app you can demo — the tracer bullet.
3. **Phases 6–9** layer on the actual product value (notes, export, settings).
4. **Phases 10–11** make it feel finished and ship it.

Suggested milestones: **M1** = end-to-end live transcript (end of Phase 5) · **M2** = transcript → notes → export (end of Phase 8) · **M3** = configurable, polished, signed release (end of Phase 11).