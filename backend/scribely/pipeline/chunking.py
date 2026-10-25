"""Transcript formatting, token estimates, and chunking for map-reduce."""

from __future__ import annotations

import math

from scribely.models import TranscriptSegment

# Conservative across tokenizers (English averages ~4 chars/token). Estimating avoids
# tokenizer downloads and works for every provider.
CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def format_segment(segment: TranscriptSegment) -> str:
    return f"[{int(segment.start)}s] {segment.text}"


def chunk_segments(
    segments: list[TranscriptSegment], max_tokens: int, overlap_tokens: int
) -> list[list[TranscriptSegment]]:
    """Split into chunks of at most ``max_tokens`` (estimated), each starting with up to
    ``overlap_tokens`` of the previous chunk's tail so nothing is cut mid-thought."""
    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    size = 0
    for segment in segments:
        cost = estimate_tokens(format_segment(segment)) + 1
        if current and size + cost > max_tokens:
            chunks.append(current)
            carry: list[TranscriptSegment] = []
            carried = 0
            for prev in reversed(current):
                prev_cost = estimate_tokens(format_segment(prev)) + 1
                if carried + prev_cost > overlap_tokens or len(carry) + 1 >= len(current):
                    break
                carry.insert(0, prev)
                carried += prev_cost
            current, size = carry, carried
        current.append(segment)
        size += cost
    if current:
        chunks.append(current)
    return chunks


def render_chunk(segments: list[TranscriptSegment]) -> str:
    return "\n".join(format_segment(s) for s in segments)
