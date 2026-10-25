from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete
from sqlalchemy.orm import Session

import airlens
from airlens.db.models import ModelVersion
from airlens.db.session import get_engine

registry = pytest.importorskip("airlens.models.registry")  # butuh mlflow (image trainer/dev)


class FakeClient:
    def __init__(self):
        self.aliases = {}

    def get_model_version_by_alias(self, name, alias):
        if alias not in self.aliases:
            raise RuntimeError("RESOURCE_DOES_NOT_EXIST")
        return type("MV", (), {"version": self.aliases[alias]})()

    def set_registered_model_alias(self, name, alias, version):
        self.aliases[alias] = str(version)


@pytest.fixture
def env():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    eng = get_engine()
    with Session(eng) as s:
        s.execute(delete(ModelVersion))
        s.commit()
    return eng, FakeClient()


def test_promote_then_rollback_without_ping_pong(env):
    eng, client = env
    for v in ("1", "2", "3"):  # 1 -> 2 -> 3 dipromosikan berurutan
        registry.set_production(eng, v, client)
    assert client.aliases["production"] == "3"
    # rollback pertama: 3 -> 2
    prev = registry.previous_production(eng, "3")
    assert prev == "2"
    registry.set_production(eng, prev, client)
    registry.mark_rolled_back(eng, "3")
    # rollback kedua harus mundur ke 1, BUKAN kembali ke 3 (versi yang ditarik)
    assert registry.previous_production(eng, "2") == "1"
    with Session(eng) as s:
        stages = {r.version: r.stage for r in s.query(ModelVersion)}
    assert stages == {"1": "archived", "2": "production", "3": "archived"}


def test_repromoting_clears_rolled_back_flag(env):
    eng, client = env
    registry.set_production(eng, "1", client)
    registry.set_production(eng, "2", client)
    registry.mark_rolled_back(eng, "2")
    registry.set_production(eng, "2", client)  # dipromosikan lagi lewat make promote
    registry.set_production(eng, "3", client)
    assert registry.previous_production(eng, "3") == "2"
