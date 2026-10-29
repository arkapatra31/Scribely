# Scribely
Listen, learn, and let Scribely take the notes — live, on-device transcription + LLM-structured study notes.

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 22+, pnpm 10, Rust (stable), and the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for your OS. PDF export also needs the Pango library: `brew install pango` on macOS (on Windows, the GTK3 runtime — see WeasyPrint's install guide). The app points the backend at Homebrew's libraries itself; if you start the backend from a terminal on an Apple Silicon Mac, run `export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` first.

```bash
# once: backend deps (isolated virtualenv in backend/.venv, nothing installed globally)
cd backend && uv sync && cd ..

# run — from repo root
pnpm install
pnpm dev                         # opens the app; it starts and stops the backend itself

# optional: run the backend on its own (e.g. to watch its logs); the app will reuse it
cd backend && uv run scribely-backend   # http://127.0.0.1:8765/health
```

`pnpm dev` opens the app and starts the backend for you (`uv run scribely-backend` in `backend/`), and stops it when you quit. If a backend is already running on port 8765 (e.g. you started one in a terminal to watch its logs), the app uses that one instead.

**First run:** a short setup asks for the lecture language and a speech model (downloaded once, with progress), checks the macOS *Screen & System Audio Recording* permission, and points you to the notes model. Change any of it later in **Settings**.

**Recording:** press **Record** (or **⌘⇧⌥R** / **Ctrl+Shift+Alt+R** from any app), play a lecture, and the transcript streams in. The dock shows the audio level, a **Pause/Resume** button (paused time is left out of the timer and timestamps), and the spoken language, which you can change at any time. Closing the window keeps Scribely in the tray / menu bar, where you can also start, pause and stop; quit from the tray menu or with ⌘Q.

**After a session:** **✦ Summarize** writes notes, **Restructure** rewrites them as a study outline, Q&A or a condensed version, **Edit** lets you fix them by hand, and **Export** saves a PDF (styled like the app) or a standalone web page — notes plus the full transcript — to `data/exports/`. The search box above the session list finds sessions by title, notes or transcript and jumps to the matching line.

**Notes (Summarize):** click the ⚙ Settings button, pick the provider and model (Azure OpenAI `gpt-4o` by default; Anthropic, OpenAI, Gemini, Ollama also supported), fill in the Azure endpoint and deployment if you use Azure, and paste your API key. Press **Test connection**, then open a stopped session and press **✦ Summarize**. The API key is never saved: it's kept in memory until Scribely closes, so you enter it each time you start the app. Alternatively, export the provider's env var (e.g. `AZURE_OPENAI_API_KEY`) before starting the backend.

**Troubleshooting:** the backend logs to `data/logs/scribely.log` (rotated, never leaves your computer). **Settings → Help → Copy diagnostics** copies versions, settings and recent log lines — never API keys or transcripts — for a bug report.

Configuration: copy `config.toml.example` to `config.toml` at the project root and edit. When running from source, all app data stays inside the project in `data/` (the SQLite database, downloaded Whisper models, exports, logs); it's gitignored. The speech model and language, and the notes model, chosen in the app override `config.toml`. API keys go in environment variables (see the example file). See `CLAUDE.md` for project rules and `PLAN.md` for the build plan.
