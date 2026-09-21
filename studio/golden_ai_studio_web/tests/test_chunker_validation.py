"""Chunker Validation Tests — P1.4B.

Validates that the SentenceChunker handles edge cases correctly:
- Abbreviations (Dr., Sr., etc.)
- Numbers and decimals
- Currency (R$ 1.500,00)
- URLs
- Version numbers (1.4.2)
- Lists
- Long phrases without punctuation
- No absurdly small chunks
- No excessive buffering
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.streaming.sentence_chunker import SentenceChunker, Chunk


class TestChunkerEdgeCases:
    """Test chunker with various edge cases."""

    def test_abbreviation_dr(self):
        """Dr. should not trigger sentence end."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Dr. Smith esta aqui.")
        # Should only emit at the final period
        assert len(chunks) == 1
        assert "Dr. Smith" in chunks[0].text

    def test_abbreviation_sr(self):
        """Sr. should not trigger sentence end."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Sr. Silva foi la.")
        assert len(chunks) == 1
        assert "Sr. Silva" in chunks[0].text

    def test_abbreviation_eng(self):
        """English abbreviations (Mr., Mrs., etc.)."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Mr. John arrived.")
        assert len(chunks) == 1

    def test_decimal_number(self):
        """Decimal numbers should not break."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("O valor e 3.14 reais.")
        # Should emit at final period
        assert len(chunks) >= 1

    def test_currency_brl(self):
        """Brazilian currency format."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Custo R$ 1.500,00.")
        assert len(chunks) == 1
        assert "R$ 1.500,00" in chunks[0].text

    def test_version_number(self):
        """Version numbers like 1.4.2."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Versao 1.4.2 lancada.")
        # Should emit at final period after "lancada"
        assert len(chunks) == 1

    def test_url(self):
        """URLs should not be broken."""
        c = SentenceChunker(min_chars=2)
        c.feed("Acesse https://example.com/path?q=1")
        c.feed(" para mais info.")
        chunks = c.flush()
        assert chunks is not None
        assert "https://example.com" in chunks.text

    def test_url_with_port(self):
        """URL with port number."""
        c = SentenceChunker(min_chars=2)
        c.feed("Servidor em http://localhost:8080/api")
        c.feed(" esta rodando.")
        chunks = c.flush()
        assert "localhost:8080" in chunks.text

    def test_list_items(self):
        """List items should be handled."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("1. Primeiro item. 2. Segundo item.")
        assert len(chunks) >= 1

    def test_long_phrase_no_punctuation(self):
        """Long phrase without punctuation should force emit at max_chars."""
        c = SentenceChunker(min_chars=2, max_chars=50)
        chunks = c.feed("Esta e uma frase muito longa sem nenhuma pontuacao")
        # Should force emit due to max_chars
        assert len(chunks) == 1
        assert len(chunks[0].text) <= 60  # Allow some margin

    def test_no_absurdly_small_chunks(self):
        """Chunks should not be absurdly small."""
        c = SentenceChunker(min_chars=10)
        c.feed("Hi. ")
        c.feed("Hello. ")
        c.feed("How are you?")
        chunks = c.flush()
        # Chunks should be at least min_chars
        if chunks:
            assert len(chunks.text) >= 10

    def test_no_excessive_buffering(self):
        """Should not buffer entire response waiting for punctuation."""
        c = SentenceChunker(min_chars=2, max_chars=30)
        tokens = ["Word "] * 20  # 20 tokens of 5 chars each
        all_chunks = []
        for token in tokens:
            all_chunks.extend(c.feed(token))
        remaining = c.flush()
        if remaining:
            all_chunks.append(remaining)
        # Should have emitted multiple chunks due to max_chars
        assert len(all_chunks) >= 3

    def test_multi_sentence_mixed(self):
        """Multiple sentences with abbreviations."""
        c = SentenceChunker(min_chars=2)
        text = "Dr. Silva disse: 'Ola! Tudo bem?' Sim, otimo."
        chunks = c.feed(text)
        # Should emit at least once
        assert len(chunks) >= 1

    def test_ellipsis(self):
        """Ellipsis (...) should not break chunker."""
        c = SentenceChunker(min_chars=2)
        # Ellipsis ends with . so it's emitted immediately
        chunks = c.feed("Espere...")
        assert len(chunks) == 1
        assert "Espere..." in chunks[0].text

    def test_exclamation_multiple(self):
        """Multiple exclamation marks."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Uau!!! Isso e incrivel!")
        assert len(chunks) >= 1

    def test_question_answer(self):
        """Question followed by answer."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Como vai? Bem, obrigado.")
        # Should emit at least at the final period
        assert len(chunks) >= 1

    def test_nested_quotes(self):
        """Text with nested quotes."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed('Ele disse: "Ola" e foi.')
        assert len(chunks) >= 1

    def test_empty_input(self):
        """Empty input should produce nothing."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("")
        assert len(chunks) == 0
        remaining = c.flush()
        assert remaining is None

    def test_only_punctuation(self):
        """Only punctuation should not crash."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("...!!!???")
        # Should not crash, may or may not emit
        assert isinstance(chunks, list)

    def test_chunk_index_sequential(self):
        """Chunk indices should be sequential."""
        c = SentenceChunker(min_chars=2)
        all_chunks = []
        for t in ["First sentence. ", "Second sentence. ", "Third sentence."]:
            all_chunks.extend(c.feed(t))
        remaining = c.flush()
        if remaining:
            all_chunks.append(remaining)
        indices = [ch.index for ch in all_chunks]
        assert indices == list(range(len(indices)))

    def test_flush_preserves_pending(self):
        """Flush should preserve pending text."""
        c = SentenceChunker(min_chars=2)
        c.feed("No terminator here")
        chunk = c.flush()
        assert chunk is not None
        assert chunk.text == "No terminator here"
        assert chunk.is_final is True

    def test_final_chunk_marked(self):
        """Final chunk should be marked as is_final."""
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Only one sentence.")
        # Sentence ends with . so it's emitted, flush returns None
        assert len(chunks) == 1
        assert chunks[0].is_final is False  # Not final until flush
        remaining = c.flush()
        assert remaining is None  # Nothing pending


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
