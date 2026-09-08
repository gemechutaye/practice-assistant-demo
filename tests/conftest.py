"""Dedicated databases keep queue tests away from a running demonstration worker."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from services.assistant.store import Store


@pytest.fixture(scope="module")
def isolated_store():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip(
            "Set TEST_DATABASE_URL to an isolated PostgreSQL server with database-creation permission"
        )
    name = "pa_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    store = Store(make_conninfo(database_url, dbname=name))
    try:
        with store.connection() as conn:
            for path in sorted(Path("supabase/migrations").glob("*.sql")):
                if path.name.startswith(("001_", "002_", "004_")):
                    conn.execute(path.read_text())
        yield store
    finally:
        with psycopg.connect(database_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()",
                (name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def demo_office(isolated_store):
    user_id = "test-user-" + uuid4().hex
    workspace_id = isolated_store.create_workspace(user_id)
    actor = isolated_store.get_actor(workspace_id, user_id, "doctor")
    yield isolated_store, actor
    with isolated_store.connection() as conn:
        conn.execute("DELETE FROM pa_workspaces")
