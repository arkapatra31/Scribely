# Set up Scribely on Windows

This guide takes you from a fresh clone to exporting your first set of notes. It assumes Windows 10 (22H2) or Windows 11, 64-bit.

Scribely runs from source for now (there's no installer yet). Everything it downloads or saves stays inside the cloned folder, in `data\`.

## 1. Install the tools

Open **PowerShell** (no need to run as administrator; winget asks for permission when it needs it).

**Git, uv (Python), Node.js and Rust:**

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Rustlang.Rustup -e
```

**Microsoft C++ Build Tools** (the Rust shell needs the MSVC compiler):

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

**WebView2** (the engine the app window uses) is already part of Windows 10 and 11. If the window later stays blank, install it with `winget install --id Microsoft.EdgeWebView2Runtime -e`.

**Pango for PDF export** (optional; everything else works without it). Install MSYS2, then Pango inside it:

```powershell
winget install --id MSYS2.MSYS2 -e
C:\msys64\usr\bin\bash.exe -lc "pacman -S --noconfirm mingw-w64-ucrt-x86_64-pango"
```

Scribely's PDF library looks in `C:\msys64\ucrt64\bin` automatically.

**Close PowerShell and open a new one** so the new tools are on your PATH. Then install pnpm and check everything:

```powershell
npm install -g pnpm@10
git --version; uv --version; node --version; pnpm --version; cargo --version
```

Node should be v22 or newer, pnpm v10.

> If PowerShell says running scripts is disabled when you call `pnpm`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

> uv keeps Scribely's Python and its libraries in `backend\.venv`. Nothing is installed into a system Python.

## 2. Clone the repository

```powershell
git clone https://github.com/arkapatra31/Scribely.git
cd Scribely
```

## 3. Install Scribely's dependencies

```powershell
cd backend; uv sync; cd ..   # Python backend (downloads Python 3.12 if needed)
pnpm install                 # desktop app
```

## 4. (Optional) Configuration file

Scribely works without one: you choose the speech model, language and notes model inside the app. To change advanced defaults (for example the compute device or chunk sizes):

```powershell
Copy-Item config.toml.example config.toml
```

Settings chosen in the app override the file.

## 5. Start Scribely

```powershell
pnpm dev
```

The first start compiles the Rust shell, which takes several minutes; later starts take seconds. The Scribely window opens and starts the backend by itself. You'll briefly see "Starting Scribely…".

Keep this PowerShell window open while you use Scribely; its output is useful if something goes wrong. If Windows Firewall asks about network access, you can decline: Scribely's backend only listens on `127.0.0.1`.

## 6. First-run setup

A short setup appears the first time:

1. **Welcome**: press **Get started**.
2. **How should Scribely listen?**
   - **Spoken language**: choose the language of your lectures (for example English). This makes the transcript faster and more accurate than auto-detect.
   - **Speech model**: **Small** is a good default. Pick **Tiny** or **Base** on an older PC, **Large v3 Turbo** for best accuracy on a fast one. Press **Download and use** (or **Download**) and wait for the progress bar to reach 100%. The model is saved in `data\models\` and only downloads once.
3. **Let Scribely hear your computer**: Windows needs no permission for this; you'll see a green confirmation. Scribely records the sound playing on your **default output device** (speakers or headphones), never your microphone.
4. **Choose a notes model**: press **Set up the notes model** (or do it later in Settings; recording works without it).
   - Pick a **provider**:
     - **Azure OpenAI**: fill in **Endpoint** (`https://<resource>.openai.azure.com/`), **Deployment**, and the **Model** behind it (e.g. `gpt-4o`).
     - **OpenAI**, **Anthropic** or **Gemini**: pick or type a model.
     - **Ollama** (free, fully offline): install it with `winget install --id Ollama.Ollama -e`, run `ollama pull llama3.1` (or any model), then pick it from the list.
   - Paste your **API key** (not needed for Ollama). It's kept in memory only and forgotten when Scribely quits, so you'll paste it again next time. Alternatively, set the provider's environment variable before starting, e.g. `$env:ANTHROPIC_API_KEY = "..."` then `pnpm dev`.
   - Press **Save**, then **Test connection**. You should see "Connected to …".
5. Press **Start using Scribely**.

## 7. Record a lecture

1. Open a lecture video in any browser or player, with sound on (headphones are fine).
2. In Scribely, press the red **Record** button, or press **Ctrl+Shift+Alt+R** from any app.
3. Play the video. Within a second or two:
   - the transcript appears line by line, with a grey live preview of the sentence in progress;
   - the **level meter** in the dock moves with the audio. If it stays flat for a few seconds you'll see "No sound yet — is it playing?";
   - the **language chip** in the dock shows the spoken language; you can change it at any time.
4. **Pause**: press the pause button in the dock when you pause the video. The timer stops and paused time is left out of the timestamps. Press it again to resume.
5. **Work in the background**: close the Scribely window. Scribely keeps running in the **system tray** (bottom-right of the taskbar; it may be under the **^** arrow). Left-click the icon to show the window again; right-click it to stop, pause/resume or quit.
6. **Stop**: press the square **Stop** button, choose **Stop recording** in the tray menu, or press **Ctrl+Shift+Alt+R** again.

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

- **PDF document**: styled like the app, with page numbers; the full transcript follows on its own pages. Needs Pango (step 1).
- **Web page**: a single HTML file that opens in any browser, light or dark, with links from the notes to the transcript.

Files are saved to `data\exports\`. Press **Show in Explorer** in the confirmation banner to open the folder.

## 11. Settings and help

Open **Settings** (bottom of the sidebar):

- **Speech**: change the language or switch speech models (new models download with progress).
- **Notes model**: provider, model, API key, **Test connection**.
- **Help**: the keyboard shortcut, and **Copy diagnostics**, which copies versions, settings and recent log lines (never keys or transcripts) for a bug report.

Logs are written to `data\logs\scribely.log`.

## 12. Quit

Right-click the tray icon and choose **Quit Scribely** (closing the window only hides it). The backend stops with the app. Next time, start it with `pnpm dev` from the `Scribely` folder.

## Updating

```powershell
git pull
cd backend; uv sync; cd ..
pnpm install
pnpm dev
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Transcript stays empty, level meter flat | Make sure sound plays on the **default** output device (Settings → System → Sound → Output). Scribely records that device; audio sent to another device isn't heard. |
| "Can't reach the Scribely backend" | Check the PowerShell output for an error. Running `cd backend; uv sync` again usually fixes missing libraries. |
| `pnpm dev` fails with a linker or `link.exe` error | The C++ Build Tools are missing; rerun the Build Tools command in step 1 and open a new PowerShell. |
| Speech model download fails | Check your internet connection and press **Retry** in Settings → Speech. |
| Summarize says the API key is missing | Keys are forgotten when Scribely quits; paste it again in Settings → Notes model. |
| Ollama model not found | Run `ollama pull <model>` and pick it in Settings. |
| PDF export says Pango is missing | Install MSYS2 and Pango as in step 1, then restart Scribely. |
| The shortcut does nothing | Another app may own Ctrl+Shift+Alt+R; the PowerShell output says so at start. Use the Record button or the tray menu. |
| Can't find Scribely after closing the window | It's in the system tray, possibly under the **^** arrow. |
