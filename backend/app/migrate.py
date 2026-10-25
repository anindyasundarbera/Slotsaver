"""Minimal, explicit schema management for the POC.

Why not Alembic: this POC has a single linear schema with no production data.
`Base.metadata.create_all` creates missing tables, and `verify_schema` fails loudly
when an existing database is older than the models, so a stale DB can never be
served silently. Postgres deployments should add Alembic before going live.
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect

from .config import get_settings
from .db import Base, get_engine


def create_schema() -> list[str]:
    settings = get_settings()
    engine = get_engine(settings.database_url)
    before = set(inspect(engine).get_table_names())
    Base.metadata.create_all(engine)
    after = set(inspect(engine).get_table_names())
    return sorted(after - before)


def verify_schema() -> list[str]:
    """Return the list of missing tables (empty means the schema is current)."""
    settings = get_settings()
    engine = get_engine(settings.database_url)
    existing = set(inspect(engine).get_table_names())
    expected = set(Base.metadata.tables)
    return sorted(expected - existing)


def main() -> int:
    created = create_schema()
    missing = verify_schema()
    if created:
        print(f"created tables: {', '.join(created)}")
    if missing:
        print(f"ERROR missing tables: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("schema ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
