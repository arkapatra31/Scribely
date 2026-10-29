# Scribely
Listen, learn, and let Scribely take the notes — live, on-device transcription + LLM-structured study notes.

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 22+, pnpm 10, Rust (stable), and the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for your OS.

```bash
# once: backend deps (isolated virtualenv in backend/.venv, nothing installed globally)
cd backend && uv sync && cd ..

# run — from repo root
pnpm install
pnpm dev                         # opens the app; it starts and stops the backend itself

# optional: run the backend on its own (e.g. to watch its logs); the app will reuse it
cd backend && uv run scribely-backend   # http://127.0.0.1:8765/health
```

`pnpm dev` opens the app and starts the backend for you (`uv run scribely-backend` in `backend/`), and stops it when you quit. If a backend is already running on port 8765 (e.g. you started one in a terminal to watch its logs), the app uses that one instead. Press **Record**, play a lecture, and the transcript streams in.

After a session: **✦ Summarize** writes notes, **Restructure** rewrites them as a study outline, Q&A or a condensed version, **Edit** lets you fix them by hand, and **Export** saves a standalone HTML file (notes + full transcript) to `data/exports/`.

**Notes (Summarize):** click the ⚙ Settings button, pick the provider and model (Azure OpenAI `gpt-4o` by default; Anthropic, OpenAI, Gemini, Ollama also supported), fill in the Azure endpoint and deployment if you use Azure, and paste your API key. Press **Test connection**, then open a stopped session and press **✦ Summarize**. The API key is never saved: it's kept in memory until Scribely closes, so you enter it each time you start the app. Alternatively, export the provider's env var (e.g. `AZURE_OPENAI_API_KEY`) before starting the backend.

Configuration: copy `config.toml.example` to `config.toml` at the project root and edit. When running from source, all app data stays inside the project in `data/` (the SQLite database, downloaded Whisper models, exports); it's gitignored. API keys go in environment variables (see the example file). See `CLAUDE.md` for project rules and `PLAN.md` for the build plan.
