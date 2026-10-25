"""``uv run scribely-capture-check``: record a few seconds of system audio to verify capture.

Writes what Scribely hears (16 kHz mono, the STT input format) to a WAV file and prints the
signal level, so capture can be checked on real hardware before the rest of the app exists.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import wave
from pathlib import Path

import numpy as np

from scribely.capture import TARGET_SAMPLE_RATE, CaptureError, create_capture
from scribely.capture.dsp import Float32Array
from scribely.config import ConfigError, load_settings

SILENCE_RMS = 1e-4


async def record(seconds: float) -> tuple[Float32Array, float]:
    """Return the captured samples and the timeline length (chunk end offset) in seconds."""
    capture = create_capture(load_settings().capture)
    chunks: list[Float32Array] = []
    timeline_end = 0.0

    async def consume() -> None:
        nonlocal timeline_end
        async for chunk in capture.stream():
            chunks.append(chunk.samples)
            timeline_end = chunk.end

    await capture.start()
    consumer = asyncio.create_task(consume())
    try:
        await asyncio.wait({consumer}, timeout=seconds)
    finally:
        await capture.stop()
        await consumer  # re-raises a backend failure
    samples = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return samples, timeline_end


def write_wav(path: Path, samples: Float32Array) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TARGET_SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--seconds", type=float, default=10.0, help="how long to record")
    parser.add_argument("--output", type=Path, default=Path("capture-check.wav"))
    args = parser.parse_args(argv)

    print(f"Recording {args.seconds:g}s of system audio. Play something now…")
    try:
        samples, timeline_end = asyncio.run(record(args.seconds))
    except (ConfigError, CaptureError) as err:
        print(err, file=sys.stderr)
        raise SystemExit(2) from None

    write_wav(args.output, samples)
    captured = len(samples) / TARGET_SAMPLE_RATE
    rms = float(np.sqrt(np.mean(samples**2))) if len(samples) else 0.0
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    print(f"Saved {args.output} ({captured:.1f}s captured, timeline {timeline_end:.1f}s)")
    print(f"Level: RMS {rms:.4f}, peak {peak:.4f}")
    if rms < SILENCE_RMS:
        print(
            "Warning: the recording is silent. Is audio playing on the default output device?",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
