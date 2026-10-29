"""Streaming loop: capture chunks -> VAD-cut speech segments -> timestamped transcript.

Audio accumulates in a buffer. Every ``VAD_STEP_SECONDS`` the buffer is run through the VAD:
- a pause of ``min_silence_ms`` after speech finalizes that speech as one segment;
- speech reaching ``max_segment_seconds`` is cut at its longest pause (or hard-cut);
- otherwise, a fast rough transcription of the in-progress speech is emitted as a partial.
A discontinuity in the capture timeline (a silence gap) also finalizes the buffer.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from scribely.capture.base import AudioChunk
from scribely.capture.dsp import TARGET_SAMPLE_RATE, Float32Array
from scribely.config import SttConfig
from scribely.stt.transcriber import Transcriber
from scribely.stt.vad import SpeechDetector

SR = TARGET_SAMPLE_RATE
VAD_STEP_SECONDS = 0.5
GAP_TOLERANCE_SECONDS = 0.1
PROMPT_CHARS = 200

RunBlocking = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Utterance:
    start: float
    """Seconds from capture start."""
    end: float
    text: str
    final: bool
    """False for a live partial that a later utterance will replace."""


class StreamingTranscriber:
    """Turns a capture stream into utterances. Create one per recording session."""

    def __init__(
        self,
        transcriber: Transcriber,
        vad: SpeechDetector,
        cfg: SttConfig,
        *,
        run_blocking: RunBlocking = asyncio.to_thread,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transcriber = transcriber
        self._vad = vad
        self._cfg = cfg
        self._run_blocking = run_blocking
        self._clock = clock
        self._min_silence = int(cfg.min_silence_ms * SR / 1000)
        self._pad = int(cfg.speech_pad_ms * SR / 1000)
        self._max_segment = int(cfg.max_segment_seconds * SR)
        self._buf: Float32Array = np.zeros(0, dtype=np.float32)
        self._buf_start = 0.0
        self._prompt = ""
        self._next_partial_at = 0.0  # clock() time

    async def run(self, chunks: AsyncIterator[AudioChunk]) -> AsyncIterator[Utterance]:
        unchecked = 0
        step = int(VAD_STEP_SECONDS * SR)
        async for chunk in chunks:
            if chunk.boundary:
                async for u in self._flush():
                    yield u
                unchecked = 0
                continue
            if len(self._buf) and chunk.start - self._buf_end > GAP_TOLERANCE_SECONDS:
                async for u in self._flush():
                    yield u
            if not len(self._buf):
                self._buf_start = chunk.start
            self._buf = np.concatenate([self._buf, chunk.samples])
            unchecked += len(chunk.samples)
            if unchecked >= step:
                unchecked = 0
                async for u in self._step():
                    yield u
        async for u in self._flush():
            yield u

    @property
    def _buf_end(self) -> float:
        return self._buf_start + len(self._buf) / SR

    async def _step(self) -> AsyncIterator[Utterance]:
        spans: list[tuple[int, int]] = await self._run_blocking(self._vad.speech_spans, self._buf)
        n = len(self._buf)
        if not spans:
            self._drop(max(0, n - self._pad))  # keep a little audio for a speech onset
            return
        first, last_end = spans[0][0], spans[-1][1]
        if n - last_end >= self._min_silence:
            async for u in self._finalize(first, last_end):
                yield u
            self._drop(last_end)
        elif n - first >= self._max_segment:
            cut = _longest_pause_cut(spans) or n
            async for u in self._finalize(first, cut, pad_end=False):
                yield u
            self._drop(cut)
        elif self._cfg.partial_interval_seconds > 0 and self._clock() >= self._next_partial_at:
            async for u in self._partial(first):
                yield u

    async def _flush(self) -> AsyncIterator[Utterance]:
        if len(self._buf):
            spans = await self._run_blocking(self._vad.speech_spans, self._buf)
            if spans:
                async for u in self._finalize(spans[0][0], spans[-1][1]):
                    yield u
        self._drop(len(self._buf))

    async def _finalize(self, a: int, b: int, *, pad_end: bool = True) -> AsyncIterator[Utterance]:
        a = max(0, a - self._pad)
        b = min(len(self._buf), b + self._pad) if pad_end else b
        offset = self._buf_start + a / SR
        texts = await self._run_blocking(
            lambda: self._transcriber.transcribe(self._buf[a:b], final=True, prompt=self._prompt)
        )
        for t in texts:
            yield Utterance(
                offset + t.start, min(offset + t.end, offset + (b - a) / SR), t.text, True
            )
        if texts:
            self._prompt = " ".join([self._prompt, *(t.text for t in texts)])[-PROMPT_CHARS:]
        self._next_partial_at = 0.0

    async def _partial(self, a: int) -> AsyncIterator[Utterance]:
        a = max(0, a - self._pad)
        audio = self._buf[a:]
        started = self._clock()
        texts = await self._run_blocking(
            lambda: self._transcriber.transcribe(audio, final=False, prompt=self._prompt)
        )
        took = self._clock() - started
        # Back off when the machine can't keep up, so partials never starve final segments.
        self._next_partial_at = started + max(self._cfg.partial_interval_seconds, 2 * took)
        if texts:
            offset = self._buf_start + a / SR
            yield Utterance(
                offset + texts[0].start,
                offset + len(audio) / SR,
                " ".join(t.text for t in texts),
                False,
            )

    def _drop(self, n: int) -> None:
        if n <= 0:
            return
        self._buf = self._buf[n:]
        self._buf_start += n / SR


def _longest_pause_cut(spans: list[tuple[int, int]]) -> int | None:
    """Midpoint of the longest gap between consecutive speech spans, if any."""
    gaps = [
        (b_start - a_end, (a_end + b_start) // 2)
        for (_, a_end), (b_start, _) in itertools.pairwise(spans)
    ]
    if not gaps:
        return None
    return max(gaps)[1]
