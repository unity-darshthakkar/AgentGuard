"""Fresh PostgreSQL migration regression test.

This test is opt-in. Set TEST_POSTGRES_DATABASE_URL only to a disposable
PostgreSQL database; it must never point at Neon production.
"""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.database import normalize_database_url
from app.core.config import get_settings


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_DATABASE_URL"),
    reason="requires an explicitly supplied disposable PostgreSQL database",
)
def test_empty_postgres_migrates_to_head():
    url = os.environ["TEST_POSTGRES_DATABASE_URL"]
    engine = create_engine(normalize_database_url(url))
    inspector = inspect(engine)
    assert inspector.get_table_names() == []

    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", normalize_database_url(url).replace("%", "%%"))
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    command.upgrade(alembic_config, "head")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"agents", "transactions", "security_events", "agent_credentials", "authorization_decisions"} <= tables
    assert inspector.get_foreign_keys("agent_credentials")[0]["referred_table"] == "agents"
    assert any(i["name"] == "ix_agents_status_created" for i in inspector.get_indexes("agents"))
    with engine.connect() as connection:
        revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    assert revision == "add0db8b111a"
