"""``uv run scribely-transcribe-check``: live-transcribe system audio in the terminal.

Runs the configured capture backend through VAD + faster-whisper and prints partial
hypotheses (updated in place) and final timestamped segments. Stop with Ctrl+C.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import time

from scribely.capture import CaptureError, create_capture
from scribely.config import ConfigError, load_settings
from scribely.stt import SileroVAD, StreamingTranscriber, STTError, Utterance, WhisperTranscriber


def fmt_time(seconds: float) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes):02d}:{secs:04.1f}"


class Printer:
    def __init__(self) -> None:
        self._partial_shown = False

    def show(self, u: Utterance) -> None:
        width = shutil.get_terminal_size().columns
        if u.final:
            self._clear()
            print(f"[{fmt_time(u.start)} → {fmt_time(u.end)}] {u.text}", flush=True)
        else:
            line = f"… {u.text}"
            if len(line) > width - 1:
                line = "…" + line[-(width - 2) :]
            self._clear()
            print(line, end="", flush=True)
            self._partial_shown = True

    def _clear(self) -> None:
        if self._partial_shown:
            print("\r\033[2K", end="")
            self._partial_shown = False


async def transcribe(seconds: float | None) -> int:
    settings = load_settings()
    transcriber = WhisperTranscriber(settings.stt, settings.paths.resolved_models_dir())
    print(
        f'Loading speech model "{settings.stt.model}" '
        "(the first run downloads it; this can take a few minutes)…",
        flush=True,
    )
    started = time.monotonic()
    await asyncio.to_thread(transcriber.load)
    print(f"Model ready in {time.monotonic() - started:.1f}s.", flush=True)

    capture = create_capture(settings.capture)
    stream = StreamingTranscriber(transcriber, SileroVAD(settings.stt.vad_threshold), settings.stt)
    printer = Printer()
    count = 0

    async def consume() -> None:
        nonlocal count
        async for u in stream.run(capture.stream()):
            printer.show(u)
            count += u.final

    await capture.start()
    print("Listening — play something. Ctrl+C to stop.\n", flush=True)
    consumer = asyncio.create_task(consume())
    try:
        await asyncio.wait({consumer}, timeout=seconds)
    finally:
        await capture.stop()
        await consumer  # drains the last segment; re-raises backend failures
    return count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--seconds", type=float, default=None, help="stop after this long")
    args = parser.parse_args(argv)
    try:
        count = asyncio.run(transcribe(args.seconds))
    except KeyboardInterrupt:
        print("\nStopped.")
        return
    except (ConfigError, CaptureError, STTError) as err:
        print(err, file=sys.stderr)
        raise SystemExit(2) from None
    print(f"\n{count} segment(s) transcribed.")


if __name__ == "__main__":
    main()
