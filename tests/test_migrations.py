from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

import airlens
from airlens.db.session import get_engine

ALEMBIC_INI = Path(airlens.__file__).parent / "db" / "alembic.ini"
TABLES = {"predictions", "iqair_readings", "model_versions", "monitoring_reports", "iqair_requests"}


@pytest.fixture
def alembic_cfg():
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    return cfg


def _tables():
    return set(inspect(get_engine()).get_table_names()) - {"alembic_version"}


def test_upgrade_downgrade_roundtrip(alembic_cfg):
    command.downgrade(alembic_cfg, "base")
    assert _tables() == set()
    command.upgrade(alembic_cfg, "head")
    assert _tables() == TABLES
    command.downgrade(alembic_cfg, "base")
    assert _tables() == set()
    command.upgrade(alembic_cfg, "head")
    assert _tables() == TABLES


def test_models_match_migrations(alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    # Gagal bila models.py berubah tanpa migrasi baru.
    command.check(alembic_cfg)
