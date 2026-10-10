import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _write_entries(path, entries):
    path.mkdir(parents=True, exist_ok=True)
    target = path / "journal_2026-10-05.jsonl"
    target.write_text("".join(json.dumps(item) + "\n" for item in entries),
                      encoding="utf-8")
    return target


def test_history_reader_is_read_only_allowlisted_and_conservative(tmp_path):
    from trade_journal import TradeJournal

    journal_dir = tmp_path / "journal"
    pending = {
        "setup_id": "pending-1", "timestamp": "2026-10-05T10:00:00",
        "symbol": "BTCUSD", "direction": "BUY", "result": "PENDING",
        "trade_opened": False, "trade_ticket": 0, "ai_analysis": "private thesis",
    }
    imported = {
        "setup_id": "import-1", "timestamp": "2026-10-05T09:00:00",
        "symbol": "BTCUSD", "direction": "SELL", "result": "WIN",
        "confidence": "IMPORTED_MT5", "ai_model": "MT5_IMPORT",
        "trade_opened": True, "trade_ticket": 123, "profit_usd": 20,
    }
    execution_claim = {
        "setup_id": "claim-1", "symbol": "BTCUSD", "result": "WIN",
        "ai_model": "AUTO_TRADE", "trade_opened": True, "trade_ticket": 456,
    }
    unresolved_provenance = {
        "setup_id": "legacy-1", "symbol": "BTCUSD", "result": "LOSS",
        "actual_rr": -1.0, "account": "private-account",
    }
    target = _write_entries(journal_dir,
                            [pending, imported, execution_claim, unresolved_provenance])
    before = target.read_bytes()

    page = TradeJournal(journal_dir=journal_dir).get_history_page(
        symbol="BTCUSD", limit=10)

    assert page["ok"] is True and page["read_only"] is True
    assert page["proven_execution_supported"] is False
    by_id = {row["record_id"]: row for row in page["records"]}
    assert by_id["pending-1"]["record_type"] == "PENDING_ANALYSIS"
    assert by_id["pending-1"]["execution_status"] == "NOT_EXECUTED"
    assert by_id["import-1"]["record_type"] == "IMPORTED_MT5"
    assert by_id["import-1"]["execution_status"] == "NOT_REAL_ACCOUNT_VERIFIED"
    assert by_id["claim-1"]["record_type"] == "EXECUTION_UNVERIFIED"
    assert by_id["legacy-1"]["record_type"] == "JOURNAL_RESULT_UNVERIFIED"
    assert all("ai_analysis" not in row and "account" not in row and "profit_usd" not in row
               for row in page["records"])
    assert all("PROVEN" not in row["execution_status"] for row in page["records"])
    assert target.read_bytes() == before


def test_history_reader_missing_directory_and_bounds_do_not_create_files(tmp_path):
    from trade_journal import TradeJournal

    missing = tmp_path / "not-created"
    journal = TradeJournal(journal_dir=missing)
    result = journal.get_history_page()
    assert result["status"] == "UNAVAILABLE"
    assert not missing.exists()
    assert journal.get_history_page(limit=11)["error_code"] == "INVALID_LIMIT"
    assert journal.get_history_page(offset=-1)["error_code"] == "INVALID_OFFSET"
    assert journal.get_history_page(record_type="EXECUTED")["error_code"] == "INVALID_RECORD_TYPE"
    assert not missing.exists()


def test_history_reader_filters_raw_calendar_dates_symbol_and_unrecorded_exit(tmp_path):
    from trade_journal import TradeJournal

    journal_dir = tmp_path / "journal"
    target = _write_entries(journal_dir, [
        {"setup_id": "today-btc", "timestamp": "2026-10-05T08:30:00-03:00",
         "symbol": "BTCUSD", "result": "WIN"},
        {"setup_id": "yesterday-btc", "timestamp": "2026-10-04T23:30:00Z",
         "symbol": "BTCUSD", "result": "LOSS"},
        {"setup_id": "today-eur", "timestamp": "2026-10-05T11:00:00",
         "symbol": "EURUSD", "result": "BREAKEVEN"},
        {"setup_id": "invalid-date", "timestamp": "2026-10-05garbage",
         "symbol": "BTCUSD", "result": "PENDING"},
    ])
    before = target.read_bytes()
    journal = TradeJournal(journal_dir=journal_dir)

    yesterday = journal.get_history_page(
        date_from="2026-10-04", date_to="2026-10-04", limit=10)
    assert [row["record_id"] for row in yesterday["records"]] == ["yesterday-btc"]
    assert yesterday["records"][0]["timestamp"].endswith("Z")
    assert yesterday["date_basis"] == "RAW_TIMESTAMP_CALENDAR_DATE_NO_TZ_CONVERSION"

    selected = journal.get_history_page(
        symbol="BTCUSD", date_from="2026-10-05", date_to="2026-10-05",
        exit_type="NOT_RECORDED", limit=10)
    assert [row["record_id"] for row in selected["records"]] == ["today-btc"]
    assert selected["records"][0]["result"] == "WIN"
    assert selected["records"][0]["exit_type"] == "NOT_RECORDED"
    assert target.read_bytes() == before


def test_history_reader_validates_filters_and_paginates_after_filtering(tmp_path):
    from trade_journal import TradeJournal

    journal_dir = tmp_path / "journal"
    _write_entries(journal_dir, [
        {"setup_id": f"day-{day}-{index}",
         "timestamp": f"2026-10-{day:02d}T12:00:00",
         "symbol": "EURUSD", "result": "PENDING"}
        for day in (3, 4, 5) for index in range(4)
    ])
    journal = TradeJournal(journal_dir=journal_dir)
    first = journal.get_history_page(
        date_from="2026-10-04", date_to="2026-10-05", limit=3, offset=0)
    second = journal.get_history_page(
        date_from="2026-10-04", date_to="2026-10-05", limit=3, offset=3)
    assert len(first["records"]) == len(second["records"]) == 3
    assert set(row["record_id"] for row in first["records"]).isdisjoint(
        row["record_id"] for row in second["records"])
    assert first["has_more"] and second["has_more"]
    assert journal.get_history_page(date_from="2026-02-30")["error_code"] == "INVALID_DATE"
    assert journal.get_history_page(date_from="2026-10-05", date_to="2026-10-04")["error_code"] == "INVALID_DATE_RANGE"
    assert journal.get_history_page(exit_type="TAKE_PROFIT")["error_code"] == "UNSUPPORTED_EXIT_FILTER"
    assert journal.get_history_page(limit=10, offset=12)["records"] == []


def test_history_reader_paginates_and_honors_scan_cap(tmp_path, monkeypatch):
    import trade_journal

    journal_dir = tmp_path / "journal"
    records = [
        {"setup_id": f"row-{index}", "symbol": "EURUSD", "result": "WIN"}
        for index in range(5)
    ]
    _write_entries(journal_dir, records)
    journal = trade_journal.TradeJournal(journal_dir=journal_dir)
    first = journal.get_history_page(limit=2, offset=0)
    second = journal.get_history_page(limit=2, offset=2)
    assert len(first["records"]) == len(second["records"]) == 2
    assert set(row["record_id"] for row in first["records"]).isdisjoint(
        row["record_id"] for row in second["records"])
    assert first["has_more"] and second["has_more"]

    monkeypatch.setattr(trade_journal, "HISTORY_SCAN_MAX_RECORDS", 3)
    capped = journal.get_history_page(limit=3)
    assert capped["scanned_records"] == 3
    assert capped["scan_truncated"] is True
    assert journal.get_history_page(offset=3)["error_code"] == "INVALID_OFFSET"


def test_statistics_reader_does_not_create_journal_or_cache_directories(tmp_path, monkeypatch):
    import statistics_engine

    journal_dir = tmp_path / "absent-journal"
    data_dir = tmp_path / "absent-statistics"
    monkeypatch.setattr(statistics_engine, "JOURNAL_DIR", journal_dir)
    monkeypatch.setattr(statistics_engine, "DATA_DIR", data_dir)
    engine = statistics_engine.StatisticsEngine()
    assert engine.get_asset_performance() == {}
    assert engine.get_hourly_performance() == {}
    assert not journal_dir.exists()
    assert not data_dir.exists()


def test_canonical_statistics_snapshot_preserves_provenance_limits_without_cache_write(monkeypatch):
    import types
    from jarvis_core.golden_bridge import GoldenReadBridge

    class FixtureEngine:
        def get_strategy_performance(self): return {}
        def get_asset_performance(self): return {"XAUUSD": {"wins": 1}}
        def get_hourly_performance(self): return {}
        def get_regime_performance(self): return {}
        def get_mode_performance(self): return {}
        def get_score_calibration(self): return {}
        def get_walk_forward(self): return {}
        def get_confidence_status(self): return {}

    monkeypatch.setitem(sys.modules, "statistics_engine",
                        types.SimpleNamespace(get_engine=FixtureEngine))
    result = GoldenReadBridge.__new__(GoldenReadBridge).statistics_snapshot()
    data = result["data"]
    assert data["asset_performance"] == {"XAUUSD": {"wins": 1}}
    assert data["source"] == "trade_journal.jsonl"
    assert data["source_limit"] == 10000
    assert data["execution_provenance"] == "NOT_VERIFIED"
    assert data["mt5_imports_proven_as_real_account_trades"] is False
    assert data["cache_written"] is False


def test_journal_and_statistics_imports_have_no_directory_creation_side_effects():
    for name in ("trade_journal.py", "statistics_engine.py"):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        top_level_mkdir = [node for node in tree.body if isinstance(node, ast.Expr)
                           and isinstance(node.value, ast.Call)
                           and getattr(node.value.func, "attr", "") == "mkdir"]
        assert not top_level_mkdir, name


def test_history_tool_requires_canonical_human_confirmation_and_audit(tmp_path, monkeypatch):
    from jarvis_core import JarvisService
    from jarvis_core.runtime_profile import DEFAULT_PROFILE, WEB_AI_SAFE_PROFILE, set_active_runtime_profile

    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    reads = []
    monkeypatch.setattr(service.golden_bridge, "trade_journal_history",
                        lambda *args: reads.append(args) or {
                            "ok": True, "read_only": True, "records": [],
                        })
    try:
        tool = service.registry.get("golden_trade_journal_history")
        assert tool.confirmation is True and tool.llm_enabled is False
        assert service.runtime_profile.trading_enabled is False
        assert service.runtime_profile.tool_disabled_reason("golden_place_order") == "TRADING_DISABLED_BY_PROFILE"
        assert service.runtime_profile.tool_disabled_reason("golden_trade_journal_history") == ""
        descriptor = service.registry.capability_descriptor(tool)
        assert descriptor["side_effect_class"] == "READ_ONLY"
        assert descriptor["approval_requirements"] == ["HUMAN_CONFIRMATION"]

        request = service.execute_tool(
            "golden_trade_journal_history",
            {"symbol": "BTCUSD", "record_type": "ALL", "limit": 10,
             "offset": 0, "date_from": "", "date_to": "", "exit_type": "ALL"},
            command="history-test", task_id="fixture",
        )
        assert request.get("confirmation_required") is True, request
        assert reads == []
        result = service.confirm(request["token"], task_id="fixture")
        assert result["ok"] is True
        assert len(reads) == 1
        audit = service.audit.recent(10)
        assert any(item.get("tool") == "golden_trade_journal_history"
                   and item.get("status") == "aguardando_confirmacao" for item in audit)
        assert any(item.get("tool") == "golden_trade_journal_history"
                   and item.get("status") == "executado" for item in audit)
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_history_http_adapter_uses_jarvis_service_and_ui_does_not_query_it():
    server = (ROOT / "server_agent.py").read_text(encoding="utf-8")
    shell = (ROOT / "jarvis_ui" / "src" / "desktop-shell.js").read_text(encoding="utf-8")
    assert '"/api/jarvis/golden/trade-history": lambda d: self._api_jarvis_golden_trade_history(d)' in server
    start = server.index("    def _api_jarvis_golden_trade_history(self, data):")
    end = server.index("\n    def ", start + 8)
    handler = server[start:end]
    assert '_legacy_audit_context(' in handler
    assert '_execute_jarvis_read("golden_trade_journal_history"' in handler
    assert "_api_journal_history" not in handler
    assert "/api/journal/history" not in shell
    assert shell.count("/api/jarvis/golden/trade-history") == 1
    history_start = shell.index("function wireTradeJournalHistory")
    assert 'button.addEventListener("click", () => requestPage(0));' in shell[history_start:]
    request_call = shell.index('gateway.httpPost("/api/jarvis/golden/trade-history"', history_start)
    assert 'limit: 10, offset: targetOffset' in shell[request_call:request_call + 180]
    assert "date_from: filters.date_from" in shell
    assert "exit_type: filters.exit_type" in shell
    assert 'window.requestJarvisHttpConfirmation' in shell
    assert 'gateway.httpPost("/api/desktop/confirm", { token })' in shell
    assert 'if (route === "historico")' not in shell


def test_history_http_adapter_validates_ten_record_cap_and_forwards_filters():
    from server_agent import GoldenAIHandler

    class FakeHandler:
        def __init__(self):
            self.calls = []

        def _legacy_audit_context(self, payload, session_id, surface):
            return {"correlation_id": "fixture-correlation", "session_id": session_id,
                    "surface": surface}

        def _execute_jarvis_read(self, tool_name, arguments, audit_context=None):
            self.calls.append((tool_name, arguments, audit_context))
            return {"ok": True}

    handler = FakeHandler()
    result = GoldenAIHandler._api_jarvis_golden_trade_history(handler, {
        "symbol": "BTCUSD", "limit": 10, "offset": 20,
        "date_from": "2026-10-04", "date_to": "2026-10-05",
        "exit_type": "NOT_RECORDED",
    })
    assert result == {"ok": True}
    name, args, audit = handler.calls[0]
    assert name == "golden_trade_journal_history"
    assert args == {"symbol": "BTCUSD", "record_type": "ALL", "limit": 10,
                    "offset": 20, "date_from": "2026-10-04",
                    "date_to": "2026-10-05", "exit_type": "NOT_RECORDED"}
    assert audit["correlation_id"] == "fixture-correlation"
    assert GoldenAIHandler._api_jarvis_golden_trade_history(
        handler, {"limit": 11}) == {"ok": False, "error_code": "INVALID_PAGINATION"}
    assert len(handler.calls) == 1


def test_history_ui_is_manual_authenticated_confirmed_bounded_and_read_only():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("Node.js não disponível para teste UI mockado")

    shell = (ROOT / "jarvis_ui" / "src" / "desktop-shell.js").read_text(encoding="utf-8")
    start = shell.index("function wireTradeJournalHistory(history) {")
    workflow = shell[start:]
    harness = r"""
const vm = require('node:vm');
class Element {
  constructor(nodes={}) { this.nodes=nodes; this.dataset={}; this.children=[]; this.listeners={}; this.textContent=''; this.attrs={}; }
  querySelector(selector) { return this.nodes[selector] || null; }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  async click() { await this.listeners.click(); }
  prepend(node) { this.children.unshift(node); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=[...nodes]; }
  setAttribute(name,value) { this.attrs[name]=value; }
  getAttribute(name) { return this.attrs[name] ?? null; }
  removeAttribute(name) { delete this.attrs[name]; }
  insertAdjacentElement(_where,node) { this.inserted=node; }
}
function fixture({authenticated=true, confirmResult={ok:true,data:{records:[]}}}={}) {
  const controls=new Element(), header=new Element({'.d2HistoryExports':controls});
  const status=new Element(), state=new Element(), body=new Element();
  const filterState=new Element(), symbol=new Element(), exit=new Element(), from=new Element(), to=new Element(), customDates=new Element();
  const periods=['today','yesterday','7d','month','custom'].map(name=>{const item=new Element();item.dataset.d2HistoryPeriod=name;item.attrs['aria-pressed']=String(name==='7d');return item;});
  const nodes={'[data-history-read-status]':status,'[data-history-read-state]':state,'[data-history-read-records]':body};
  const history=new Element({'.d2HistoryHeaderPanel':header,'#d2HistoryFilterState':filterState,'[data-history-custom-dates]':customDates,'[data-history-date-from]':from,'[data-history-date-to]':to,'[data-history-symbol]':symbol,'[data-history-exit]':exit});
  history.querySelectorAll=(selector)=>selector==='[data-d2-history-period]'?periods:[];
  let options=null, requested=null; const calls=[];
  const window={Gateway:{isAuthenticated:authenticated,async httpPost(path,data){calls.push({path,data}); if(path==='/api/desktop/confirm') return typeof confirmResult==='function'?confirmResult(requested):confirmResult; if(path==='/api/security/deny') return {ok:true}; requested=data; return {ok:true,confirmation_required:true,token:'single-use-secret'};}},requestJarvisHttpConfirmation(value){options=value;return true;}};
  const document={createElement(){return new Element(nodes);}};
  const context={history,window,document};
  vm.runInNewContext(process.argv[1]+'; wireTradeJournalHistory(history);',context);
  const button=controls.children[0];
  const resultPanel=header.inserted;
  const pagination=resultPanel.children[0], pager=pagination.children[1];
  return {button,status,state,body,calls,filterState,periods,symbol,exit,from,to,customDates,previous:pager.children[0],pageLabel:pager.children[1],next:pager.children[2],getOptions:()=>options,getRequest:()=>requested};
}
(async()=>{
  const cancelled=fixture();
  if(cancelled.calls.length!==0) throw new Error('history queried on open');
  await cancelled.button.click();
  if(cancelled.calls.length!==1 || cancelled.calls[0].path!=='/api/jarvis/golden/trade-history') throw new Error('manual canonical request missing');
  const request=cancelled.calls[0].data;
  if(request.limit!==10 || request.offset!==0) throw new Error('initial page not bounded');
  if(!/^\d{4}-\d{2}-\d{2}$/.test(request.date_from) || request.date_from>request.date_to) throw new Error('default period not materialized');
  const cancelOptions=cancelled.getOptions();
  cancelOptions.onCancel();
  if(cancelled.calls.length!==2 || cancelled.calls[1].path!=='/api/security/deny' || cancelled.body.children.length!==0 || !cancelled.status.textContent.includes('cancelada')) throw new Error('cancel did not consume approval without reading');
  if(cancelled.status.textContent.includes('single-use-secret')) throw new Error('token exposed in UI');

  const success=fixture({confirmResult:(request)=>({ok:true,data:{read_only:true,has_more:request.offset===0,date_basis:'RAW_TIMESTAMP_CALENDAR_DATE_NO_TZ_CONVERSION',date_from:request.date_from||null,date_to:request.date_to||null,symbol:request.symbol,exit_type_filter:request.exit_type,scan_truncated:false,records:Array.from({length:request.offset===0?14:4},(_,i)=>({timestamp:'t'+i,symbol:'EURUSD',direction:'BUY',record_type:'IMPORTED_MT5',execution_status:'NOT_REAL_ACCOUNT_VERIFIED',exit_type:'NOT_RECORDED',private_field:'do-not-render'}))}})});
  await success.button.click();
  const approved=success.getOptions();
  const response=await approved.onApprove('single-use-secret');
  approved.onComplete(response);
  if(success.calls.length!==2 || success.calls[1].path!=='/api/desktop/confirm') throw new Error('confirmation did not use canonical endpoint');
  if(success.body.children.length!==10) throw new Error('UI exceeded 10 returned records');
  if(success.body.children.some(row=>row.children.length!==6 || row.children.some(cell=>cell.textContent.includes('do-not-render')))) throw new Error('non-allowlisted journal fields rendered');
  if(!success.status.textContent.includes('10 registro')) throw new Error('confirmed results not shown');
  if(success.next.disabled) throw new Error('next page was not enabled by has_more');
  await success.next.click();
  const pageTwo=success.getOptions();
  if(success.calls[2].data.offset!==10 || success.calls[2].data.limit!==10) throw new Error('next page offset invalid');
  const pageTwoResult=await pageTwo.onApprove('single-use-secret'); pageTwo.onComplete(pageTwoResult);
  if(success.body.children.length!==4 || !success.next.disabled || success.previous.disabled) throw new Error('page two navigation state incorrect '+JSON.stringify({rows:success.body.children.length,next:success.next.disabled,previous:success.previous.disabled,page:success.pageLabel.textContent,request:success.calls[2].data,status:success.status.textContent}));
  const yesterday=success.periods.find(item=>item.dataset.d2HistoryPeriod==='yesterday');
  await yesterday.click();
  if(success.body.children.length!==0 || success.filterState.textContent.includes('FILTROS ALTERADOS')===false) throw new Error('filter change retained mismatched rows');
  success.symbol.value='BTCUSD';
  await success.button.click();
  const filtered=success.calls[4].data;
  if(filtered.offset!==0 || filtered.symbol!=='BTCUSD' || filtered.date_from!==filtered.date_to) throw new Error('filter did not reset pagination/apply date and symbol');
  const filteredOptions=success.getOptions();
  const filteredResult=await filteredOptions.onApprove('single-use-secret'); filteredOptions.onComplete(filteredResult);

  const today=fixture();
  await today.periods.find(item=>item.dataset.d2HistoryPeriod==='today').click();
  await today.button.click();
  if(today.calls[0].data.date_from!==today.calls[0].data.date_to) throw new Error('today bounds are not a single calendar date');
  today.getOptions().onCancel();

  const month=fixture();
  await month.periods.find(item=>item.dataset.d2HistoryPeriod==='month').click();
  await month.button.click();
  if(!month.calls[0].data.date_from.endsWith('-01') || month.calls[0].data.date_to<month.calls[0].data.date_from) throw new Error('month boundaries invalid');
  month.getOptions().onCancel();

  const custom=fixture(); custom.from.value='2026-09-01'; custom.to.value='2026-09-30';
  await custom.periods.find(item=>item.dataset.d2HistoryPeriod==='custom').click();
  if(custom.customDates.hidden) throw new Error('custom date inputs remain hidden');
  await custom.button.click();
  if(custom.calls[0].data.date_from!=='2026-09-01' || custom.calls[0].data.date_to!=='2026-09-30') throw new Error('custom date range not applied');
  custom.getOptions().onCancel();

  const invalidCustom=fixture(); invalidCustom.from.value='2026-10-02'; invalidCustom.to.value='2026-10-01';
  await invalidCustom.periods.find(item=>item.dataset.d2HistoryPeriod==='custom').click();
  await invalidCustom.button.click();
  if(invalidCustom.calls.length!==0 || !invalidCustom.status.textContent.includes('intervalo')) throw new Error('invalid custom range reached Gateway');

  const oldCore=fixture({confirmResult:{ok:true,data:{read_only:true,has_more:false,scan_truncated:false,date_basis:'RAW_TIMESTAMP_CALENDAR_DATE_NO_TZ_CONVERSION',date_from:null,date_to:null,symbol:'',exit_type_filter:'ALL',records:[{timestamp:'2026-10-04'}]}}});
  await oldCore.button.click(); const oldCoreOptions=oldCore.getOptions();
  const oldCoreResult=await oldCoreOptions.onApprove('single-use-secret'); oldCoreOptions.onComplete(oldCoreResult);
  if(oldCore.body.children.length!==0 || !oldCore.status.textContent.includes('filtros')) throw new Error('response from an old reader claimed filters were applied');

  const unavailable=fixture({confirmResult:{ok:true,data:{read_only:true,status:'UNAVAILABLE',reason:'JOURNAL_DIRECTORY_MISSING',records:[]}}});
  await unavailable.button.click(); const unavailableOptions=unavailable.getOptions();
  const unavailableResult=await unavailableOptions.onApprove('single-use-secret'); unavailableOptions.onComplete(unavailableResult);
  if(!unavailable.status.textContent.includes('JOURNAL_DIRECTORY_MISSING') || unavailable.status.textContent.includes('Nenhum registro corresponde')) throw new Error('unavailable Journal was shown as an empty result');

  const expired=fixture({confirmResult:{ok:false,error:'invalid or expired'}});
  await expired.button.click();
  const expiredOptions=expired.getOptions();
  const denied=await expiredOptions.onApprove('expired-token');
  expiredOptions.onFailure(denied);
  if(expired.calls.length!==2 || expired.body.children.length!==0 || !expired.status.textContent.includes('inválida ou expirada')) throw new Error('invalid/expired token did not fail closed');

  const unauthenticated=fixture({authenticated:false});
  await unauthenticated.button.click();
  if(unauthenticated.calls.length!==0 || !unauthenticated.status.textContent.includes('autenticada')) throw new Error('unauthenticated request was sent');
})().catch(error=>{process.stderr.write(error.stack||String(error));process.exitCode=1;});
"""
    completed = subprocess.run(
        [node, "-e", harness, workflow], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert '/api/jarvis/golden/panel-analysis' not in workflow
    assert 'market-data' not in workflow.lower()
    assert 'gemini' not in workflow.lower()

    app = (ROOT / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    assert "window.requestJarvisHttpConfirmation" in app
    assert "handlers.onApprove(_confirmToken)" in app
    assert 'window.Gateway.confirmAction(_confirmToken, true)' in app
    assert "handlers.onCancel?.()" in app


def test_existing_confirmation_modal_requires_human_click_and_fails_closed():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("Node.js não disponível para teste mockado do modal")

    app = (ROOT / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    start = app.index("let _confirmToken = null;")
    end = app.index("\nasync function runBoot()", start)
    modal = app[start:end]
    harness = r"""
const vm=require('node:vm');
function fixture(confirmResponse={ok:true}) {
  const element=()=>{const events={};return {hidden:true,dataset:{},textContent:'',className:'',disabled:false,events,addEventListener(name,fn){events[name]=fn;}};};
  const dialog=element(),risk=element(),action=element(),message=element(),approve=element(),deny=element(),status=element();
  const nodes={'#confirmDialog':dialog,'#confirmRisk':risk,'#confirmAction':action,'#confirmMessage':message,'#confirmApprove':approve,'#confirmDeny':deny,'#confirmStatus':status};
  const calls=[]; let completed=0,cancelled=0,failed=0;
  const window={Gateway:{isAuthenticated:true,async httpPost(path,data){calls.push({path,data});return confirmResponse;},confirmAction(){throw new Error('WS confirmation should not be used');}}};
  const context={window,document:{addEventListener(){}},$:selector=>nodes[selector],setState(){}};
  vm.runInNewContext(process.argv[1]+'; wireConfirmationDialog();',context);
  const opened=window.requestJarvisHttpConfirmation({token:'temporary-secret',action:'Consultar histórico',message:'Confirmar leitura?',onApprove:token=>window.Gateway.httpPost('/api/desktop/confirm',{token}),onComplete(){completed++;},onCancel(){cancelled++;},onFailure(){failed++;}});
  if(!opened || dialog.hidden) throw new Error('human confirmation modal did not open');
  if(calls.length!==0) throw new Error('token consumed before human approval');
  if([risk.textContent,action.textContent,message.textContent,status.textContent].join(' ').includes('temporary-secret')) throw new Error('token exposed in modal');
  return {calls,dialog,approve,deny,get counts(){return {completed,cancelled,failed};}};
}
(async()=>{
  const approved=fixture({ok:true});
  await approved.approve.events.click();
  if(approved.calls.length!==1 || approved.calls[0].path!=='/api/desktop/confirm' || approved.calls[0].data.token!=='temporary-secret') throw new Error('approval did not make exactly one canonical HTTP confirmation');
  if(approved.counts.completed!==1 || !approved.dialog.hidden) throw new Error('approved result not completed');

  const cancelled=fixture({ok:true});
  cancelled.deny.events.click(); if(cancelled.calls.length!==0 || cancelled.counts.cancelled!==1) throw new Error('cancel consumed token or failed to cancel');

  const expired=fixture({ok:false,error:'invalid or expired'}); await expired.approve.events.click(); if(expired.calls.length!==1 || expired.counts.failed!==1 || expired.counts.completed!==0 || !expired.dialog.hidden) throw new Error('invalid/expired confirmation did not fail closed');
})().catch(error=>{process.stderr.write(error.stack||String(error));process.exitCode=1;});
"""
    completed = subprocess.run(
        [node, "-e", harness, modal], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
