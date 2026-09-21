from __future__ import annotations

import json
import platform
import socket
from pathlib import Path
from uuid import uuid4


def load_identity(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("identificador"):
                return data
        except json.JSONDecodeError:
            pass
    identity = {
        "identificador": uuid4().hex,
        "nome_computador": socket.gethostname(),
        "sistema_operacional": platform.system() or "Windows",
    }
    path.write_text(json.dumps(identity, indent=2), encoding="utf-8")
    return identity
