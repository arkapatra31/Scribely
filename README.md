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

Configuration: copy `config.toml.example` to `config.toml` and edit. API keys go in environment variables (see the example file). See `CLAUDE.md` for project rules and `PLAN.md` for the build plan.
