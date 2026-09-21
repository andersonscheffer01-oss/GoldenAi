from __future__ import annotations

import shutil
from pathlib import Path


def restore_checkpoint_file(checkpoint_path: str | Path, source_path: str | Path) -> None:
    shutil.copy2(Path(checkpoint_path), Path(source_path))
