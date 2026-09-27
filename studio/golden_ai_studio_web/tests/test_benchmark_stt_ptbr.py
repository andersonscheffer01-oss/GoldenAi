from __future__ import annotations

import json

from tools.benchmark_stt_ptbr import edit_counts, load_manifest, normalize


def test_normalize_handles_case_accents_and_punctuation() -> None:
    assert normalize("  Olá, JARVIS!  ") == "olá jarvis"


def test_edit_counts_returns_word_level_wer_components() -> None:
    assert edit_counts("abra o bloco", "abra bloco") == (0, 1, 0, 3)
    assert edit_counts("abra o bloco", "abra o editor") == (1, 0, 0, 3)


def test_manifest_accepts_only_licensed_fixture_entries(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source": "test corpus",
                "license": "CC-BY-4.0",
                "fixtures": [
                    {
                        "fixture_id": "licensed-1",
                        "path": "licensed.wav",
                        "provenance_class": "LICENSED_TEST_FIXTURE",
                        "license": "CC-BY-4.0",
                    },
                    {
                        "fixture_id": "unknown-1",
                        "path": "unknown.wav",
                        "provenance_class": "UNKNOWN",
                    },
                    {
                        "fixture_id": "unlicensed-1",
                        "path": "unlicensed.wav",
                        "provenance_class": "LICENSED_TEST_FIXTURE",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    source, license_name, fixtures = load_manifest(manifest)

    assert source == "test corpus"
    assert license_name == "CC-BY-4.0"
    assert [item["fixture_id"] for item in fixtures] == ["licensed-1"]
