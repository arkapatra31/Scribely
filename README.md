# Scribely
Listen, learn, and let Scribely take the notes — live, on-device transcription + LLM-structured study notes.

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 22+, pnpm 10, Rust (stable), and the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for your OS.

```bash
# backend — isolated virtualenv in backend/.venv, nothing installed globally
cd backend
uv sync
uv run scribely-backend          # http://127.0.0.1:8765/health

# desktop app — from repo root
pnpm install
pnpm gen:schemas                 # TS types from backend Pydantic models
pnpm dev                         # opens the Tauri window
```

Run the backend and `pnpm dev` side by side: the window connects to `ws://127.0.0.1:8765/ws` (override with `VITE_SCRIBELY_WS_URL`). Press **Record**, play a lecture, and the transcript streams in. The app doesn't launch the backend itself yet (Phase 5.1).

**Notes (Summarize):** click the ⚙ Settings button, pick the provider and model (Azure OpenAI `gpt-4o` by default; Anthropic, OpenAI, Gemini, Ollama also supported), fill in the Azure endpoint and deployment if you use Azure, and paste your API key. Press **Test connection**, then open a stopped session and press **✦ Summarize**. The API key is never saved: it's kept in memory until Scribely closes, so you enter it each time you start the app. Alternatively, export the provider's env var (e.g. `AZURE_OPENAI_API_KEY`) before starting the backend.

Configuration: copy `config.toml.example` to `config.toml` and edit. API keys go in environment variables (see the example file). See `CLAUDE.md` for project rules and `PLAN.md` for the build plan.
