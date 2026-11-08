"""Local read-only HTTP panel for Golden Scalper Arena reports."""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = PROJECT_ROOT / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from golden_scalper_arena.dashboard_data import build_dashboard_model, render_dashboard_html


def load_report(path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_dashboard_file(report_path, output_path) -> Path:
    report = load_report(report_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard_html(build_dashboard_model(report)), encoding="utf-8")
    return output


def make_handler(report_path):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, content: bytes, content_type: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):  # noqa: N802 - stdlib handler API
            try:
                report = load_report(report_path)
                model = build_dashboard_model(report)
                if self.path.rstrip("/") == "/api/report":
                    self._send(json.dumps(model, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                elif self.path.rstrip("/") in {"", "/dashboard.html"}:
                    self._send(render_dashboard_html(model).encode("utf-8"), "text/html; charset=utf-8")
                else:
                    self._send(b"Not found", "text/plain; charset=utf-8", 404)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._send(json.dumps({"error": str(exc)}).encode("utf-8"), "application/json; charset=utf-8", 500)

        def log_message(self, *_args):
            return

    return Handler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="../Data/experiments/latest_report.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Path(args.report)))
    print(f"Golden Scalper Arena panel: http://{args.host}:{args.port}/")
    print("READ-ONLY / SIMULATION-ONLY / execution_authority=NONE")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

