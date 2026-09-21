from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, inspect, select, text


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scalar_counts(connection, metadata: MetaData) -> dict[str, int]:
    return {table.name: int(connection.execute(select(func.count()).select_from(table)).scalar_one()) for table in metadata.sorted_tables}


def financial_total(connection, metadata: MetaData) -> int:
    table = metadata.tables.get("lancamentos_financeiros")
    if table is None or "valor_centavos" not in table.c:
        return 0
    return int(connection.execute(select(func.coalesce(func.sum(table.c.valor_centavos), 0))).scalar_one())


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra o SQLite local do Golden Jarvis para PostgreSQL.")
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--postgres", required=True)
    parser.add_argument("--uploads-root", default="/opt/golden-jarvis/uploads/pending")
    parser.add_argument("--report", type=Path, default=Path("migration-report.json"))
    args = parser.parse_args()

    sqlite_path = args.sqlite.resolve()
    if not sqlite_path.is_file():
        raise SystemExit("Banco SQLite de origem nao encontrado.")
    if not args.postgres.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("Destino deve ser uma URL PostgreSQL.")

    source_engine = create_engine(f"sqlite:///{sqlite_path.as_posix()}", future=True)
    target_engine = create_engine(args.postgres, future=True)
    source_meta = MetaData()
    source_meta.reflect(bind=source_engine)
    target_meta = MetaData()
    target_meta.reflect(bind=target_engine)

    missing = set(source_meta.tables) - set(target_meta.tables)
    if missing:
        raise SystemExit(f"Tabelas ausentes no PostgreSQL: {sorted(missing)}. Inicie o backend uma vez para criar o schema.")

    report = {"started_at": datetime.now(timezone.utc).isoformat(), "sqlite_sha256": sha256(sqlite_path)}
    with source_engine.connect() as source, target_engine.begin() as target:
        existing = sum(int(target.execute(select(func.count()).select_from(target_meta.tables[name])).scalar_one()) for name in source_meta.tables)
        if existing:
            raise SystemExit("PostgreSQL de destino nao esta vazio; migracao recusada para evitar duplicidade.")

        source_counts = scalar_counts(source, source_meta)
        source_total = financial_total(source, source_meta)
        for source_table in source_meta.sorted_tables:
            target_table = target_meta.tables[source_table.name]
            rows = [dict(row) for row in source.execute(select(source_table)).mappings()]
            if source_table.name == "arquivos":
                for row in rows:
                    row["caminho_seguro"] = str(Path(args.uploads_root) / row["nome_interno"])
            if rows:
                target.execute(target_table.insert(), rows)

        for table in target_meta.sorted_tables:
            if "id" in table.c:
                target.execute(text("SELECT setval(pg_get_serial_sequence(:table, 'id'), COALESCE((SELECT MAX(id) FROM \"" + table.name + "\"), 1), true)"), {"table": table.name})

        target_counts = scalar_counts(target, target_meta)
        target_total = financial_total(target, target_meta)
        if source_counts != {name: target_counts[name] for name in source_counts}:
            raise RuntimeError("Contagens divergentes; transacao revertida.")
        if source_total != target_total:
            raise RuntimeError("Total financeiro divergente; transacao revertida.")

    report.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "tables": source_counts,
        "financial_total_centavos": source_total,
        "status": "validated",
    })
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
