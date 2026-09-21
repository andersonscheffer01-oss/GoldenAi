from __future__ import annotations

import difflib
import hashlib
from pathlib import Path


def unified_diff(original: str | Path, working: str | Path) -> str:
    original_path = Path(original)
    working_path = Path(working)
    original_lines = original_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    working_lines = working_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            original_lines,
            working_lines,
            fromfile=str(original_path),
            tofile=str(working_path),
        )
    )


def diff_hash(diff_text: str) -> str:
    return hashlib.sha256(str(diff_text).encode("utf-8")).hexdigest().upper()
