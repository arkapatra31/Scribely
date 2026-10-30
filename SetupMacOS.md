# Set up Scribely on macOS

This guide takes you from a fresh clone to exporting your first set of notes. It assumes macOS 13 (Ventura) or later, on Apple Silicon or Intel.

Scribely runs from source for now (there's no installer yet). Everything it downloads or saves stays inside the cloned folder, in `data/`.

## 1. Install the tools

Open **Terminal**.

**Xcode Command Line Tools** (compilers for the Rust shell):

```bash
xcode-select --install
```

**Homebrew** (skip if you have it; see [brew.sh](https://brew.sh)):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Git, uv (Python) and Node.js 22:**

```bash
brew install git uv node@22
brew link --overwrite node@22
npm install -g pnpm@10
```

**Rust:**

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
```

Check everything is there:

```bash
git --version && uv --version && node --version && pnpm --version && cargo --version
```

Node should be v22 or newer, pnpm v10.

> uv keeps Scribely's Python and its libraries in `backend/.venv`. Nothing is installed into your system Python.

## 2. Clone the repository

```bash
git clone https://github.com/arkapatra31/Scribely.git
cd Scribely
```

## 3. Install Scribely's dependencies

```bash
cd backend && uv sync && cd ..   # Python backend (downloads Python 3.12 if needed)
pnpm install                     # desktop app
```

## 4. (Optional) Configuration file

Scribely works without one: you choose the speech model, language and notes model inside the app. Create it only to change advanced defaults, such as where Scribely keeps its data:

```bash
cp config.toml.example config.toml
```

`config.toml` sits in the repo root next to `config.toml.example` and is gitignored, so your paths and settings stay private. (`backend/scribely/config.py` is the code that reads it; don't edit that.)

**Where Scribely keeps your data.** By default everything lives in `data/` inside the clone:

| Folder | Contents |
| --- | --- |
| `data/scribely.db` | sessions, transcripts, notes, settings |
| `data/models/` | downloaded speech models, one `models--<publisher>--<repo>` folder each |
| `data/exports/` | exported PDFs and web pages |
| `data/logs/` | `scribely.log` (rotated) |

To keep them elsewhere, for example speech models on an external drive, uncomment and edit the `[paths]` section:

```toml
[paths]
data_dir = "/Users/<you>/ScribelyData"        # moves all of the above
# or move only some folders:
# models_dir = "/Volumes/External/ScribelyModels"
# exports_dir = "/Users/<you>/Documents/Scribely"
# logs_dir = "/Users/<you>/ScribelyData/logs"
```

Absolute paths, `~/...`, and paths relative to the repo root all work. Restart Scribely after editing. Existing files aren't moved for you: move the folders yourself, or let Scribely download the models again.

Settings chosen in the app (speech model, language, notes model) override the file; folder locations can only be set here.

## 5. Start Scribely

```bash
pnpm dev
```

The first start compiles the Rust shell, which takes a few minutes; later starts take seconds. The Scribely window opens and starts the backend by itself. You'll briefly see "Starting Scribely…".

Keep this Terminal window open while you use Scribely; its output is useful if something goes wrong.

## 6. First-run setup

A short setup appears the first time:

1. **Welcome**: press **Get started**.
2. **How should Scribely listen?**
   - **Spoken language**: choose the language of your lectures (for example English). This makes the transcript faster and more accurate than auto-detect.
   - **Speech model**: **Small** is a good default. Pick **Tiny** or **Base** on an older Mac, **Large v3 Turbo** for best accuracy on a fast one. Press **Download and use** (or **Download**) and wait for the progress bar to reach 100%. The model is saved in `data/models/` and only downloads once.
3. **Let Scribely hear your computer**: macOS needs the **Screen & System Audio Recording** permission for Scribely to hear audio, even though it never records the screen.
   - Press **Allow access**. When macOS asks, allow it. If it doesn't ask, press **Open System Settings**.
   - In **System Settings → Privacy & Security → Screen & System Audio Recording**, turn on the app you started Scribely from: **Terminal** (or iTerm, VS Code, …) when running from source.
   - **Quit and restart Scribely** for the permission to take effect: press ⌘Q in Scribely, then run `pnpm dev` again. Setup opens again with your language and model already saved; press **Continue** until you're back at this step, which should now show the permission as granted.
4. **Choose a notes model**: press **Set up the notes model** (or do it later in Settings; recording works without it).
   - Pick a **provider**:
     - **Azure OpenAI**: fill in **Endpoint** (`https://<resource>.openai.azure.com/`), **Deployment**, and the **Model** behind it (e.g. `gpt-4o`).
     - **OpenAI**, **Anthropic** or **Gemini**: pick or type a model.
     - **Ollama** (free, fully offline): install it from [ollama.com](https://ollama.com), run `ollama pull llama3.1` (or any model), then pick it from the list.
   - Paste your **API key** (not needed for Ollama). It's kept in memory only and forgotten when Scribely quits, so you'll paste it again next time. Alternatively, start Scribely with the provider's environment variable set, e.g. `export ANTHROPIC_API_KEY=...` before `pnpm dev`.
   - Press **Save**, then **Test connection**. You should see "Connected to …".
5. Press **Start using Scribely**.

## 7. Record a lecture

1. Open a lecture video in any browser or player, with sound on (headphones are fine).
2. In Scribely, press the red **Record** button, or press **⌘⇧⌥R** from any app.
3. Play the video. Within a second or two:
   - the transcript appears line by line, with a grey live preview of the sentence in progress;
   - the **level meter** in the dock moves with the audio. If it stays flat for a few seconds you'll see "No sound yet — is it playing?";
   - the **language chip** in the dock shows the spoken language; you can change it at any time.
4. **Pause**: press the pause button in the dock when you pause the video. The timer stops and paused time is left out of the timestamps. Press it again to resume.
5. **Work in the background**: close the Scribely window. Scribely keeps running in the **menu bar** (look for its icon; it shows **●** while recording). From its menu you can stop, pause/resume, or show the window again. Clicking the Dock icon also brings the window back.
6. **Stop**: press the square **Stop** button, choose **Stop recording** in the menu bar, or press **⌘⇧⌥R** again.

The session appears in the sidebar under **Today**. Click its title to rename it.

## 8. Turn the transcript into notes

1. Open the stopped session and press **✦ Summarize**. Progress shows next to the button; long lectures are split into parts and summarized in parallel.
2. The **Notes** tab opens: a title, a summary and sections. Click a section's time chip (e.g. `1:05 – 2:30`) to jump to that part of the transcript.
3. **Restructure** rewrites the notes as a **Study outline**, **Questions & answers** or **Condensed** version.
4. **Edit** lets you change the title, summary, headings and points by hand. Your edits are kept, and Restructure works from them.

You can come back to any saved session later and summarize it again.

## 9. Find a session

Type in the **Search sessions** box above the sidebar list. Scribely searches titles, notes and transcripts and highlights the match. Clicking a transcript hit opens the session at that line.

## 10. Export

Press **Export** and choose:

- **PDF document**: styled like the app, with page numbers; the full transcript follows on its own pages.
- **Web page**: a single HTML file that opens in any browser, light or dark, with links from the notes to the transcript.

Files are saved to `data/exports/`. Press **Show in Finder** in the confirmation banner to open the folder.

## 11. Settings and help

Open **Settings** (bottom of the sidebar):

- **Speech**: change the language or switch speech models (new models download with progress).
- **Notes model**: provider, model, API key, **Test connection**.
- **Help**: the keyboard shortcut, and **Copy diagnostics**, which copies versions, settings and recent log lines (never keys or transcripts) for a bug report.

Logs are written to `data/logs/scribely.log`.

## 12. Quit

Press **⌘Q**, or choose **Quit Scribely** in the menu-bar menu. The backend stops with the app. Next time, start it with `pnpm dev` from the `Scribely` folder.

## Updating

```bash
git pull
cd backend && uv sync && cd ..
pnpm install
pnpm dev
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Transcript stays empty, level meter flat | Make sure sound is playing on your Mac's output. Check the permission in System Settings → Privacy & Security → Screen & System Audio Recording (for your terminal app), then quit and restart Scribely. |
| "Can't reach the Scribely backend" | Check the Terminal output for an error. Running `cd backend && uv sync` again usually fixes missing libraries. |
| Speech model download fails | Check your internet connection and press **Retry** in Settings → Speech. |
| Summarize says the API key is missing | Keys are forgotten when Scribely quits; paste it again in Settings → Notes model. |
| Ollama model not found | Run `ollama pull <model>` and pick it in Settings. |
| The shortcut does nothing | Another app may own ⌘⇧⌥R; the Terminal output says so at start. Use the Record button or the menu-bar menu. |
