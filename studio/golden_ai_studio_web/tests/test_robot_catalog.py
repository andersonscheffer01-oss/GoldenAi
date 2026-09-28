import json
import inspect
import sqlite3
from pathlib import Path

from jarvis_core.robot_catalog import RobotCatalogReadModel, default_approved_roots
from jarvis_core.service import JarvisService


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _source(name="Robot Breakout", family=True, version="1.2"):
    family_line = "// strategy_family: BREAKOUT\n" if family else ""
    return (
        f'#property version "{version}"\n'
        + family_line
        + 'input string SimboloParaOperar="XAUUSD";\n'
        + 'input ENUM_TIMEFRAMES Timeframe=PERIOD_M15;\n'
        + 'input int MaximoDeOperacoesAbertas=2;\n'
        + 'input double StopLossEmPontos=300;\n'
        + 'input double TakeProfitEmPontos=600;\n'
        + 'input bool AtivarTrailingStop=true;\n'
        + 'void OnTick() {}\n'
    )


def _backtest(strategy):
    return json.dumps({
        "stats": {
            "strategy": strategy,
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "model": "OHLC",
            "period_start": 1,
            "period_end": 2,
            "initial_balance": 10000,
            "total_pnl": -12.5,
            "gross_profit": 20,
            "gross_loss": -32.5,
            "total_trades": 4,
            "win_rate": 50,
            "profit_factor": 0.61,
            "max_drawdown": 32.5,
        },
        "parameters": {"risk": 0.5},
    })


def test_discovery_has_stable_identity_and_associates_artifacts(tmp_path):
    root = tmp_path / "approved"
    _write(root / "Robot_Breakout.mq5", _source())
    _write(root / "Robot_Breakout.ex5", b"compiled fixture")
    _write(root / "Robot_Breakout.set", "Risk=0.5\n")
    _write(root / "Robot_Breakout.html", "strategy_family: BREAKOUT")
    _write(root / "backtest_Robot_Breakout.json", _backtest("Robot_Breakout"))

    catalog = RobotCatalogReadModel(approved_roots=[root])
    first = catalog.discover()
    second = catalog.discover()

    assert first["report"]["robots_discovered"] == 1
    robot = first["robots"][0]
    assert robot["source_available"] is True
    assert robot["compiled_available"] is True
    assert len(robot["parameter_presets"]) == 1
    assert robot["backtest_count"] == 1
    assert robot["strategy_family"] == "BREAKOUT"
    assert robot["status"] == "CANDIDATE"
    assert robot["forward_evidence"] == "NONE"
    assert robot["live_evidence"] == "NONE"
    assert first["robots"][0]["robot_id"] == second["robots"][0]["robot_id"]
    assert first["robots"][0]["source_artifacts"] == second["robots"][0]["source_artifacts"]


def test_compiled_only_source_only_and_unknown_are_explicit(tmp_path):
    root = tmp_path / "approved"
    _write(root / "CompiledOnly.ex5", b"opaque")
    _write(root / "SourceOnly.mq5", "#property version \"1.0\"\nvoid OnStart() {}\n")
    _write(root / "Unclear.mq5", "int value = 1;\n")

    result = RobotCatalogReadModel(approved_roots=[root]).discover()
    by_name = {item["name"]: item for item in result["robots"]}

    assert by_name["CompiledOnly"]["status"] == "DISCOVERED"
    assert "compiled artifact has no inspected source" in by_name["CompiledOnly"]["known_limitations"]
    assert by_name["SourceOnly"]["source_available"] is True
    assert by_name["Unclear"]["strategy_family"] == "UNKNOWN"


def test_user_override_survives_rescan_and_does_not_authorize_trading(tmp_path):
    root = tmp_path / "approved"
    _write(root / "Robot.mq5", _source(family=False))
    catalog = RobotCatalogReadModel(approved_roots=[root])
    catalog.discover()
    robot_id = catalog.list()["robots"][0]["robot_id"]

    changed = catalog.set_user_status(robot_id, "ACTIVE", "approved repertoire")
    assert changed["robot"]["status"] == "ACTIVE"
    catalog.discover()
    detail = catalog.detail(robot_id)["robot"]
    assert detail["status"] == "ACTIVE"
    assert detail["user_overrides"][0]["authority"] == "USER_OVERRIDE"
    assert catalog.snapshot()["trade_authority"] == "NONE"


def test_conflicting_documentation_is_preserved(tmp_path):
    root = tmp_path / "approved"
    _write(root / "ConflictRobot.mq5", _source(family=False))
    _write(root / "ConflictRobot.html", "strategy_family: BREAKOUT")
    _write(root / "ConflictRobot.xml", "strategy_family: MEAN_REVERSION")

    result = RobotCatalogReadModel(approved_roots=[root]).discover()
    robot = result["robots"][0]
    detail = RobotCatalogReadModel(approved_roots=[root])
    detail.discover()
    full = detail.detail(robot["robot_id"])["robot"]

    assert full["strategy_family"] == "CONFLICT"
    assert full["what_conflicts"]
    values = {claim["value"] for claim in full["provenance"] if claim["field"] == "strategy_family"}
    assert values >= {"BREAKOUT", "MEAN_REVERSION"}


def test_service_exposes_read_only_robot_tools_without_mt5_execution(tmp_path):
    service = JarvisService(tmp_path)
    try:
        names = {item["name"] for item in service.registry.public_catalog()}
        assert {"robot_catalog_discover", "robot_catalog_list", "robot_catalog_detail"} <= names
        catalog = service.robot_catalog_snapshot()
        assert catalog["trade_authority"] == "NONE"
        assert catalog["persistence"] == "SUBORDINATE_SQLITE"
        for tool_name in ("robot_catalog_discover", "robot_catalog_list", "robot_catalog_detail"):
            descriptor = next(item for item in service.registry.public_catalog()
                              if item["name"] == tool_name)
            assert descriptor["side_effect_class"] == "READ_ONLY"
            assert descriptor["llm_enabled"] is False
    finally:
        service.close()


def test_default_roots_are_bounded_to_golden_project():
    roots = default_approved_roots()
    assert roots[0] == Path(r"C:\GoldenAI\projetos")
    assert roots[1] == Path(r"C:\GoldenAI\studio\golden_ai_studio_web")
    assert roots[2] == Path(r"C:\GoldenAI\config\backtest_results")


def test_catalog_boundary_has_no_mt5_or_order_execution_surface():
    from jarvis_core import robot_catalog

    source = inspect.getsource(robot_catalog).casefold()
    assert "metatrader5" not in source
    assert "order_send" not in source
    assert "send_order" not in source
    assert "subprocess" not in source


def test_persistence_survives_restart_and_override_is_not_lost(tmp_path):
    root = tmp_path / "approved"
    store = tmp_path / "catalog.db"
    source = root / "Robot.mq5"
    _write(source, _source(family=False))

    first = RobotCatalogReadModel(approved_roots=[root], storage_path=store)
    first.discover()
    robot_id = first.list()["robots"][0]["robot_id"]
    first.set_user_status(robot_id, "ACTIVE", "approved repertoire")
    first.close()

    second = RobotCatalogReadModel(approved_roots=[root], storage_path=store)
    second.discover()
    detail = second.detail(robot_id)["robot"]
    assert detail["status"] == "ACTIVE"
    assert detail["user_overrides"][0]["authority"] == "USER_OVERRIDE"
    assert second.snapshot()["schema_migration"] == "CATALOG_SCHEMA_V1"
    second.close()


def test_catalog_schema_does_not_auto_migrate_unknown_version(tmp_path):
    store = tmp_path / "catalog.db"
    connection = sqlite3.connect(store)
    connection.execute("CREATE TABLE catalog_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO catalog_meta(key, value) VALUES('schema_version', '999')")
    connection.commit()
    connection.close()

    try:
        RobotCatalogReadModel(storage_path=store)
    except RuntimeError as exc:
        assert str(exc) == "ROBOT_CATALOG_SCHEMA_VERSION_UNSUPPORTED"
    else:
        raise AssertionError("unknown catalog schema version was migrated")


def test_artifact_movement_keeps_id_and_mutation_keeps_history(tmp_path):
    root = tmp_path / "approved"
    store = tmp_path / "catalog.db"
    original = root / "Robot.mq5"
    moved = root / "nested" / "Robot.mq5"
    _write(original, _source(family=False))
    catalog = RobotCatalogReadModel(approved_roots=[root], storage_path=store)
    first = catalog.discover()
    first_artifact = first["robots"][0]["source_artifacts"][0]

    moved.parent.mkdir(parents=True)
    original.rename(moved)
    second = catalog.discover()
    moved_artifact = second["robots"][0]["source_artifacts"][0]
    assert moved_artifact["artifact_id"] == first_artifact["artifact_id"]
    assert catalog._store.artifact_history(first_artifact["artifact_id"]) == ["Robot.mq5", "nested/Robot.mq5"]

    _write(moved, _source(family=False) + "// mutation\n")
    third = catalog.discover()
    assert third["robots"][0]["source_artifacts"][0]["artifact_id"] != first_artifact["artifact_id"]
    assert catalog._store.history_counts()["artifacts"] >= 2
    catalog.close()


def test_preset_fingerprint_produces_high_confidence_with_independent_context(tmp_path):
    root = tmp_path / "approved"
    _write(root / "Robot.mq5", _source(family=False))
    _write(root / "Robot.set", "risk=0.5\n")
    _write(root / "generic_backtest.json", json.dumps({
        "stats": {"strategy": "generic", "symbol": "XAUUSD", "timeframe": "M15"},
        "parameters": {"risk": 0.5},
    }))
    catalog = RobotCatalogReadModel(approved_roots=[root])
    result = catalog.discover()
    assert result["report"]["association_counts"]["HIGH_CONFIDENCE"] == 1
    assert result["robots"][0]["backtest_count"] == 1
    robot_id = result["robots"][0]["robot_id"]
    assert catalog.detail(robot_id)["robot"]["backtest_artifacts"][0]["association_status"] == "HIGH_CONFIDENCE"


def test_alias_and_conflicting_association_statuses_are_explicit(tmp_path):
    root = tmp_path / "approved"
    _write(root / "RobotAlpha.mq5", _source(family=False))
    _write(root / "RobotAlpha.html", "alias: LegacyAlpha")
    _write(root / "alias_backtest.json", _backtest("LegacyAlpha"))
    result = RobotCatalogReadModel(approved_roots=[root]).discover()
    assert result["report"]["association_counts"]["VERIFIED"] == 1
    assert result["robots"][0]["aliases"][0]["value"] == "LegacyAlpha"

    conflict_root = tmp_path / "conflict"
    _write(conflict_root / "RobotAlpha.mq5", _source(family=False))
    _write(conflict_root / "RobotBeta.mq5", _source(family=False))
    _write(conflict_root / "conflict_backtest.json", json.dumps({
        "stats": {"strategy": "RobotBeta", "ea_name": "RobotAlpha"}
    }))
    conflict = RobotCatalogReadModel(approved_roots=[conflict_root]).discover()
    assert conflict["report"]["association_counts"]["CONFLICTING"] == 1


def test_ambiguous_and_unresolved_are_not_promoted(tmp_path):
    root = tmp_path / "approved"
    _write(root / "one" / "Same.mq5", _source(family=False, version="1.0"))
    _write(root / "two" / "Same.mq5", _source(family=False, version="2.0"))
    _write(root / "backtest_ambiguous.json", _backtest("Same"))
    _write(root / "backtest_unresolved.json", _backtest("generic_family"))
    result = RobotCatalogReadModel(approved_roots=[root]).discover()
    counts = result["report"]["association_counts"]
    assert counts["AMBIGUOUS"] == 1
    assert counts["UNRESOLVED"] == 1
    assert counts["VERIFIED"] == 0
    assert counts["HIGH_CONFIDENCE"] == 0
