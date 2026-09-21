from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False, "timeout": 30} if settings.resolved_database_url.startswith("sqlite") else {}
engine = create_engine(settings.resolved_database_url, connect_args=connect_args, future=True)

if settings.resolved_database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # create_all nao adiciona colunas em bancos SQLite ja existentes.
    if engine.dialect.name == "sqlite":
        from sqlalchemy import inspect
        with engine.begin() as connection:
            table_names = set(inspect(engine).get_table_names())
            if "categorias" in table_names:
                columns = {column["name"] for column in inspect(engine).get_columns("categorias")}
                additions = {
                    "icone": "VARCHAR(40)", "categoria_pai_id": "INTEGER", "ordem": "INTEGER NOT NULL DEFAULT 0",
                    "arquivada_em": "DATETIME", "limite_mensal_centavos": "INTEGER",
                }
                for name, definition in additions.items():
                    if name not in columns:
                        connection.exec_driver_sql(f"ALTER TABLE categorias ADD COLUMN {name} {definition}")
            if "dispositivos_pc" in table_names:
                columns = {column["name"] for column in inspect(engine).get_columns("dispositivos_pc")}
                if "status_json" not in columns:
                    connection.exec_driver_sql("ALTER TABLE dispositivos_pc ADD COLUMN status_json TEXT")


def check_database() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
