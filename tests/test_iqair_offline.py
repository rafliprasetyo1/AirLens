"""Booth offline: IQAir tidak terjangkau -> pakai bacaan terakhir yang tersimpan (ditandai stale), atau pesan jelas."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete
from sqlalchemy.orm import Session

import airlens
from airlens.db.models import IqairReading, IqairRequest
from airlens.db.session import get_engine
from airlens_api.iqair import IQAirClient, IQAirUnavailable


@pytest.fixture(scope="module", autouse=True)
def _schema():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean():
    with get_engine().begin() as c:
        c.execute(delete(IqairReading))
        c.execute(delete(IqairRequest))


def offline_client() -> IQAirClient:
    # Port 9 di localhost: koneksi langsung ditolak, seperti internet putus.
    return IQAirClient("kunci-uji", get_engine(), ttl_seconds=900, timeout=1.0, base_url="http://127.0.0.1:9")


def store(city: str, aqi: int, age: timedelta) -> None:
    with Session(get_engine()) as s:
        s.add(IqairReading(city=city, state="Riau", country="Indonesia", aqi_us=aqi,
                           fetched_at=datetime.now(timezone.utc) - age))
        s.commit()


def test_offline_uses_last_stored_reading():
    store("Pekanbaru", 140, timedelta(days=3))
    store("Pekanbaru", 88, timedelta(hours=5))      # terbaru, walau jauh lewat TTL 15 menit
    r = offline_client().by_city("Pekanbaru", "Riau", "Indonesia")
    assert r.stale is True and r.aqi_us == 88


def test_offline_without_stored_reading_gives_clear_message():
    with pytest.raises(IQAirUnavailable) as e:
        offline_client().by_city("Dumai", "Riau", "Indonesia")
    assert e.value.code == "jaringan_tanpa_cache" and "belum ada data" in e.value.message


def test_offline_coords_without_known_city():
    with pytest.raises(IQAirUnavailable) as e:
        offline_client().by_coords(0.51, 101.45)
    assert e.value.code == "jaringan_tanpa_cache"


def test_non_network_errors_are_not_masked():
    store("Pekanbaru", 88, timedelta(hours=5))
    client = IQAirClient("", get_engine(), base_url="http://127.0.0.1:9")   # tanpa kunci: bukan galat jaringan
    with pytest.raises(IQAirUnavailable) as e:
        client.by_city("Pekanbaru", "Riau", "Indonesia")
    assert e.value.code == "tanpa_kunci"


def test_fresh_reading_is_not_stale():
    store("Pekanbaru", 70, timedelta(minutes=2))     # masih dalam TTL: tidak memanggil IQAir sama sekali
    r = offline_client().by_city("Pekanbaru", "Riau", "Indonesia")
    assert r.stale is False and r.cached is True and r.aqi_us == 70
