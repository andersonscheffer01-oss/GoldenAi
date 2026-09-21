"""
Golden AI - Codex Bridge Provider
Chama o Codex CLI local em modo nao interativo para analises fortes de
mercado, estrategia e MQL5 dentro do Golden.
"""
import os
import base64
import shutil
import subprocess
import tempfile
from pathlib import Path


CODEX_TIMEOUT = int(os.environ.get("GOLDEN_CODEX_TIMEOUT", "240"))
CODEX_WORKDIR = Path(os.environ.get("GOLDEN_CODEX_WORKDIR", r"C:\GoldenAI"))
CODEX_EXTRA_DIRS = [
    Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal"),
    Path(r"C:\Users\Anderson\Documents\Codex"),
]


def codex_available():
    return shutil.which("codex") is not None


def _messages_to_prompt(messages):
    parts = [
        "Voce esta respondendo dentro do Golden AI Studio.",
        "Foco: analise de mercado, estrategia, robos MQL5, risco e backtest.",
        "Voce pode ler e editar arquivos no workspace quando o usuario pedir implementacao.",
        "Ao alterar arquivos, compile/teste quando possivel e diga exatamente o que mudou.",
        "Responda em portugues do Brasil, direto e pratico.",
        "Se a pergunta envolver trading, nao prometa lucro e destaque risco quando relevante.",
    ]
    for msg in messages[-10:]:
        role = msg.get("role", "user")
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        label = "Usuario" if role == "user" else "Assistente" if role == "assistant" else "Sistema"
        parts.append(f"\n[{label}]\n{content}")
    return "\n".join(parts).strip()


def _extract_images(messages):
    image_paths = []
    temp_paths = []
    for msg in messages[-10:]:
        for raw in msg.get("images") or []:
            try:
                data = str(raw or "")
                if not data:
                    continue
                if "," in data and data.split(",", 1)[0].lower().startswith("data:"):
                    data = data.split(",", 1)[1]
                binary = base64.b64decode(data, validate=False)
                if not binary:
                    continue
                tmp = tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False)
                tmp.write(binary)
                tmp.close()
                image_paths.append(tmp.name)
                temp_paths.append(tmp.name)
            except Exception:
                continue
    return image_paths, temp_paths


class CodexProvider:
    def __init__(self):
        self.available = codex_available()

    def chat(self, messages, model=None):
        if not codex_available():
            return {"error": "Codex CLI nao encontrado no PATH. Abra o Codex Desktop ou instale/atualize o Codex CLI."}

        prompt = _messages_to_prompt(messages)
        CODEX_WORKDIR.mkdir(parents=True, exist_ok=True)
        output_path = None
        temp_image_paths = []
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                output_path = f.name
            image_paths, temp_image_paths = _extract_images(messages)

            cmd = [
                "codex",
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--sandbox",
                "workspace-write",
                "-C",
                str(CODEX_WORKDIR),
                "-o",
                output_path,
            ]
            for extra_dir in CODEX_EXTRA_DIRS:
                if extra_dir.exists():
                    cmd.extend(["--add-dir", str(extra_dir)])
            for image_path in image_paths:
                cmd.extend(["-i", image_path])
            if model:
                cmd.extend(["-m", model])
            cmd.append("-")

            proc = subprocess.run(
                cmd,
                cwd=str(CODEX_WORKDIR),
                input=prompt,
                text=True,
                capture_output=True,
                timeout=CODEX_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )

            text = ""
            if output_path and os.path.exists(output_path):
                text = Path(output_path).read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                text = (proc.stdout or "").strip()

            if proc.returncode != 0 and not text:
                err = (proc.stderr or proc.stdout or "Codex retornou erro sem detalhes.").strip()
                return {"error": err[-1200:]}
            if not text:
                return {"error": "Codex retornou resposta vazia."}
            return {"content": text}
        except subprocess.TimeoutExpired:
            return {"error": f"Tempo esgotado aguardando o Codex (mais de {CODEX_TIMEOUT}s)."}
        except Exception as e:
            return {"error": str(e)}
        finally:
            if output_path:
                try:
                    os.unlink(output_path)
                except Exception:
                    pass
            for image_path in temp_image_paths:
                try:
                    os.unlink(image_path)
                except Exception:
                    pass


codex_provider = CodexProvider()


def get_codex_provider():
    return codex_provider
