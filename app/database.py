from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_sqlite() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "tailored_resumes" in tables:
        columns = {column["name"] for column in inspector.get_columns("tailored_resumes")}
        if "match_report" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE tailored_resumes ADD COLUMN match_report JSON")
                )
    if "job_sources" in tables:
        columns = {column["name"] for column in inspector.get_columns("job_sources")}
        additions = {
            "last_status": "VARCHAR(20) DEFAULT ''",
            "last_error": "TEXT DEFAULT ''",
            "last_fetched": "INTEGER DEFAULT 0",
            "last_added": "INTEGER DEFAULT 0",
        }
        with engine.begin() as connection:
            for name, ddl in additions.items():
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE job_sources ADD COLUMN {name} {ddl}")
                    )
    if "jobs" in tables:
        columns = {column["name"] for column in inspector.get_columns("jobs")}
        job_additions = {
            "last_seen_at": "DATETIME",
            "stale": "BOOLEAN DEFAULT 0",
            "eligibility_status": "VARCHAR(10) DEFAULT ''",
        }
        with engine.begin() as connection:
            for name, ddl in job_additions.items():
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}")
                    )


def init_db() -> None:
    from app import models  # noqa: F401

    models.Base.metadata.create_all(bind=engine)
    _migrate_sqlite()
