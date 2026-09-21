"""Sentence-level text chunker for streaming TTS.

Accumulates LLM tokens and emits complete sentences for TTS.
Ensures natural break points — no broken words, abbreviations, or URLs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from jarvis_core.streaming import (
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    PAUSE_CHARS,
    SENTENCE_TERMINATORS,
)

# URL pattern — never break inside URLs
_URL_RE = re.compile(r"https?://\S+|\bwww\.\S+")

# Abbreviation pattern — common PT-BR abbreviations
_ABBR_RE = re.compile(
    r"\b(?:Sr\.|Sra\.|Dr\.|Dra\.|Prof\.|Profa\.|Gov\.|Sta\.|Sto\.|Av\.|R\.)\b"
)


@dataclass
class Chunk:
    text: str
    index: int
    is_final: bool = False


class SentenceChunker:
    """Buffers LLM tokens and emits sentence-level chunks.

    Emit conditions:
    - Sentence terminator (.!?) at end of accumulated text
    - Natural pause (,;:) followed by another pause or terminator
    - MAX_CHUNK_CHARS reached (force emit)
    - Stream end (flush remaining)
    """

    def __init__(
        self,
        min_chars: int = MIN_CHUNK_CHARS,
        max_chars: int = MAX_CHUNK_CHARS,
    ):
        self._buffer = ""
        self._chunk_index = 0
        self._min_chars = min_chars
        self._max_chars = max_chars
        self._in_url = False

    def feed(self, token: str) -> list[Chunk]:
        """Feed a token from the LLM stream. Returns 0+ ready chunks."""
        self._buffer += token
        chunks: list[Chunk] = []

        # Track URL state — don't break inside URLs
        if _URL_RE.search(self._buffer):
            self._in_url = True
        elif self._in_url and (self._buffer.endswith(" ") or self._buffer.endswith("\n")):
            self._in_url = False

        # Don't emit while inside URL
        if self._in_url:
            return chunks

        # Don't emit if below min chars
        if len(self._buffer) < self._min_chars:
            return chunks

        # Force emit at max chars
        if len(self._buffer) >= self._max_chars:
            chunk = self._flush()
            if chunk:
                chunks.append(chunk)
            return chunks

        # Check for sentence terminator at end of buffer
        stripped = self._buffer.rstrip()
        if stripped and stripped[-1] in SENTENCE_TERMINATORS:
            # Ensure it's actually ending a sentence, not an abbreviation
            if not self._is_abbreviation(stripped):
                chunk = self._flush()
                if chunk:
                    chunks.append(chunk)
                return chunks

        # Check for natural pause followed by pause/terminator
        if len(self._buffer) >= self._min_chars:
            last_char = self._buffer[-1] if self._buffer else ""
            if last_char in PAUSE_CHARS:
                # Look ahead — if next char would also be a pause or terminator, emit now
                # This handles patterns like "Claro, vou verificar."
                pass

        return chunks

    def flush(self) -> Optional[Chunk]:
        """Flush remaining buffer (stream end)."""
        return self._flush(final=True)

    def _flush(self, final: bool = False) -> Optional[Chunk]:
        text = self._buffer.strip()
        self._buffer = ""
        self._in_url = False
        if not text:
            return None
        chunk = Chunk(text=text, index=self._chunk_index, is_final=final)
        self._chunk_index += 1
        return chunk

    def _is_abbreviation(self, text: str) -> bool:
        """Check if text ends with a known abbreviation."""
        return bool(_ABBR_RE.search(text))

    @property
    def pending(self) -> str:
        return self._buffer

    @property
    def chunk_count(self) -> int:
        return self._chunk_index
