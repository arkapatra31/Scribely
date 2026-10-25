"""WAV-file capture backend for development and tests (no system audio needed)."""

from __future__ import annotations

import asyncio
import threading
import time
import wave
from pathlib import Path
from typing import Any

from scribely.capture.base import AudioCapture, CaptureError
from scribely.capture.dsp import int16_to_float32


class FileCapture(AudioCapture):
    """Streams a 16-bit PCM WAV file as if it were live system audio.

    With ``realtime=False`` the file is read as fast as the consumer keeps up, which is
    what tests want.
    """

    name = "file"

    def __init__(
        self,
        path: Path,
        *,
        realtime: bool = True,
        block_seconds: float = 0.1,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._path = path
        self._realtime = realtime
        self._block_seconds = block_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    async def _open(self) -> None:
        wav = await asyncio.to_thread(self._open_wav)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(wav,), daemon=True)
        self._thread.start()

    async def _close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join)
            self._thread = None

    def _open_wav(self) -> wave.Wave_read:
        try:
            wav = wave.open(str(self._path), "rb")  # noqa: SIM115 - closed by _run()
        except FileNotFoundError:
            raise CaptureError(f"Audio file not found: {self._path}") from None
        except (wave.Error, EOFError) as err:
            raise CaptureError(f"{self._path} is not a readable WAV file: {err}") from None
        if wav.getsampwidth() != 2:
            wav.close()
            raise CaptureError(
                f"{self._path} uses {wav.getsampwidth() * 8}-bit samples; "
                "only 16-bit PCM WAV files are supported."
            )
        return wav

    def _run(self, wav: wave.Wave_read) -> None:
        try:
            with wav:
                rate = wav.getframerate()
                channels = wav.getnchannels()
                block = max(1, int(rate * self._block_seconds))
                next_due = time.monotonic()
                while not self._stop.is_set():
                    data = wav.readframes(block)
                    if not data:
                        break
                    self._push(int16_to_float32(data, channels), rate)
                    if self._realtime:
                        next_due += self._block_seconds
                        self._stop.wait(max(0.0, next_due - time.monotonic()))
                    else:
                        # Back-pressure instead of letting the bounded queue drop audio.
                        while self._backlog_seconds() > 10 and not self._stop.is_set():
                            self._stop.wait(0.01)
        except Exception as err:
            self._fail(err)
        finally:
            self._end_of_stream()
