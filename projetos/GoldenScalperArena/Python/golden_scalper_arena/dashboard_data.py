"""Read-only view model and HTML renderer for the local Arena panel."""

from __future__ import annotations

import html
import json


OFFICIAL_AGENTS = ("momentum", "defense", "breakout", "pullback", "liquidity")


def build_dashboard_model(report: dict) -> dict:
    report = dict(report or {})
    rows = {str(row.get("agent")): dict(row) for row in report.get("agents", ())}
    agents = [rows.get(name, {
        "agent": name,
        "rank": None,
        "metrics": {"trades": 0, "net_pnl": 0.0, "profit_factor": None, "max_drawdown": 0.0},
        "trades_detail": [],
    }) for name in OFFICIAL_AGENTS]
    agents.sort(key=lambda row: row.get("rank") if row.get("rank") is not None else 999)
    validation = dict(report.get("validation") or {})
    validation.setdefault("status", "NOT_VALIDATED")
    validation.setdefault("winner", None)
    security = {
        "read_only": True,
        "simulation_only": True,
        "execution_authority": "NONE",
        "real_orders": False,
    }
    security.update(dict(report.get("security") or {}))
    return {
        "title": "Golden Scalper Arena",
        "subtitle": "Laboratório multiagente • simulação somente",
        "run": dict(report.get("run") or {}),
        "security": security,
        "configuration": dict(report.get("configuration") or {}),
        "agents": agents,
        "validation": validation,
        "top_trades": list(report.get("top_trades") or [])[:5],
        "warnings": list(report.get("warnings") or []),
    }


def _money(value) -> str:
    try:
        value = float(value or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return f"${value:,.2f}"


def _metric(row, key, default="—"):
    return (row.get("metrics") or {}).get(key, default)


def render_dashboard_html(model: dict) -> str:
    model = build_dashboard_model(model) if "security" not in model else model
    table_rows = []
    for row in model["agents"]:
        pf = _metric(row, "profit_factor")
        pf = "—" if pf is None else f"{float(pf):.2f}"
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('rank') or '—'))}</td>"
            f"<td><strong>{html.escape(str(row.get('agent', '')))}</strong></td>"
            f"<td>{_money(_metric(row, 'net_pnl', 0))}</td>"
            f"<td>{float(_metric(row, 'trades', 0)):.0f}</td>"
            f"<td>{pf}</td>"
            f"<td>{float(_metric(row, 'max_drawdown', 0)):.2f}</td>"
            "</tr>"
        )
    payload = json.dumps(model, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    run = model.get("run") or {}
    security = model.get("security") or {}
    validation = model.get("validation") or {}
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in model.get("warnings", ()))
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Golden Scalper Arena</title>
<style>
:root{{color-scheme:dark;--bg:#081018;--panel:#0d1a24;--line:#1b3948;--text:#e8f0f4;--muted:#8da6b3;--green:#19d889;--amber:#e9b949;}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 85% 0,#12332d 0,#081018 38%);color:var(--text);font:14px Segoe UI,Arial,sans-serif}}
main{{max-width:1280px;margin:0 auto;padding:28px}}h1{{margin:0 0 5px;font-size:30px}}h2{{font-size:17px;margin:0 0 16px}}.muted{{color:var(--muted)}}
.top{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:22px}}.badge{{border:1px solid #956f1a;color:var(--amber);padding:9px 12px;border-radius:6px;font-weight:700}}
.security,.cards,.panel{{background:rgba(13,26,36,.93);border:1px solid var(--line);border-radius:9px;padding:16px;margin-bottom:18px}}
.security{{display:flex;flex-wrap:wrap;gap:16px;align-items:center;color:var(--green)}}.security span{{padding-right:16px;border-right:1px solid var(--line)}}.security span:last-child{{border-right:0}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.card{{border:1px solid var(--line);padding:13px;border-radius:6px}}.card label{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase}}.card b{{display:block;margin-top:7px;font-size:18px}}
table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid var(--line);text-align:left;padding:12px 9px}}th{{color:var(--muted);font-size:11px;text-transform:uppercase}}td:nth-child(n+3){{font-variant-numeric:tabular-nums}}.ok{{color:var(--green)}}.warn{{color:var(--amber)}}.grid{{display:grid;grid-template-columns:2fr 1fr;gap:18px}}ul{{margin:0;padding-left:20px}}@media(max-width:800px){{.cards,.grid{{grid-template-columns:1fr 1fr}}.top{{display:block}}.badge{{display:inline-block;margin-top:12px}}}}@media(max-width:560px){{.cards,.grid{{grid-template-columns:1fr}}main{{padding:15px}}}}
</style></head><body><main>
<div class="top"><div><h1>Golden Scalper Arena</h1><div class="muted">Laboratório multiagente • simulação somente • XAUUSD</div></div>
<div class="badge">{html.escape(str(run.get('status', 'SEM DADOS')))} · {html.escape(str(validation.get('status', 'NOT_VALIDATED')))}</div></div>
<section class="security"><span>READ-ONLY: {str(bool(security.get('read_only'))).upper()}</span><span>SIMULATION-ONLY: {str(bool(security.get('simulation_only'))).upper()}</span><span>EXECUTION_AUTHORITY: {html.escape(str(security.get('execution_authority', 'NONE')))}</span><span>ORDENS REAIS: NÃO</span></section>
<section class="cards"><div class="card"><label>Run</label><b>{html.escape(str(run.get('run_id', '—')))}</b></div><div class="card"><label>Snapshots</label><b>{html.escape(str(run.get('snapshot_count', '—')))}</b></div><div class="card"><label>Fonte</label><b>{html.escape(str(run.get('source_kind', '—')))}</b></div><div class="card"><label>Vencedor aprovado</label><b class="warn">{html.escape(str(validation.get('winner') or 'NENHUM'))}</b></div></section>
<div class="grid"><section class="panel"><h2>Ranking da Arena</h2><table><thead><tr><th>#</th><th>Agente</th><th>Resultado líquido</th><th>Trades</th><th>Profit factor</th><th>DD</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></section>
<section class="panel"><h2>Validação</h2><p class="{'ok' if validation.get('status') == 'APPROVED' else 'warn'}"><strong>{html.escape(str(validation.get('status', 'NOT_VALIDATED')))}</strong></p><p class="muted">{html.escape(str(validation.get('reason', 'Critérios ainda não concluídos.')))}</p><h2>Avisos</h2><ul>{warnings or '<li>Sem avisos adicionais.</li>'}</ul></section></div>
<section class="panel"><h2>Dados do relatório</h2><p class="muted">Proveniência: {html.escape(str(run.get('provenance', 'não informada')))}</p><pre id="report" style="white-space:pre-wrap;color:var(--muted)"></pre></section>
<script>const arenaReport={payload};document.getElementById('report').textContent=JSON.stringify(arenaReport,null,2);</script>
</main></body></html>"""


__all__ = ["OFFICIAL_AGENTS", "build_dashboard_model", "render_dashboard_html"]

