# Scribely website

Static site for GitHub Pages: `index.html`, `styles.css`, `main.js`, bundled fonts in `fonts/`. No build step, no external requests.

- **Preview:** `python3 -m http.server -d site 8000`, then open http://localhost:8000. Python's server doesn't support range requests, so chapter jumps in the demo video only work once deployed; `npx serve site` supports them locally.
- **Deploy:** pushes to `main` that touch `site/` run `.github/workflows/pages.yml`. One-time: Settings → Pages → Source: **GitHub Actions**.

## Demo video

The "See it in action" section plays `media/scribely-demo.mp4`, with `media/scribely-demo-poster.jpg` as the still shown before it plays. The current clip was recorded from the real interface. Its sound is the lecture Scribely hears, an AI voice (Kokoro, open-source neural text-to-speech, voice `af_heart`) synced to the moment Record is pressed; the transcript and notes are demo content. To replace it with a real recording (a real lecture, real transcription, real notes, with sound):

### 1. Record on your Mac

macOS's own screen recorder (⌘⇧5, QuickTime) can't capture system audio, so use [OBS Studio](https://obsproject.com) (free):

1. In OBS, add a source: **macOS Screen Capture** → Method **Window Capture** → pick the Scribely window.
2. Add a second source: **macOS Audio Capture** → **Application** → your browser (or whatever plays the lecture), so the lecture's sound is in the recording.
3. Settings → Video: Base and Output resolution **1440x900** (or 2880x1800 on a Retina display), 30 FPS. Settings → Output → Recording format: **mp4**.
4. Size the Scribely window to fill the canvas, press **Start Recording**, then:
   - press Record in Scribely and play ~30 s of a lecture (a GenAI / AWS talk fits the rest of the site); pause and resume once;
   - stop, rename the session, press ✦ Summarize, scroll the notes;
   - Restructure → Questions & answers;
   - Export → PDF document.
5. Stop recording. Aim for 45–75 seconds; trim the start and end in any editor if needed.

OBS asks for the Screen Recording permission the first time.

### 2. Convert it for the web

From the repo root (needs `ffmpeg`, e.g. `brew install ffmpeg`):

```bash
ffmpeg -i ~/Movies/your-recording.mp4 \
  -vf "scale=1440:-2,fps=30" -c:v libx264 -preset slow -crf 24 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -movflags +faststart site/media/scribely-demo.mp4

# poster frame: pick a good moment, e.g. 40 s in (the notes)
ffmpeg -ss 40 -i site/media/scribely-demo.mp4 -frames:v 1 -q:v 3 site/media/scribely-demo-poster.jpg
```

Keep the file under ~20 MB (`-crf 26` or `28` makes it smaller).

### 3. Update the page

In `index.html`, in the `#demo` section:

- set each chapter's `data-t` to the second where that step starts in your video;
- change the caption under the player (it currently says the content is a demo).

Browsers only allow muted autoplay, so the video starts muted when it scrolls into view. The **Sound on** button unmutes it, and the big play button starts it with sound. If you ever use a clip without audio, remove the `#demoSound` button.
