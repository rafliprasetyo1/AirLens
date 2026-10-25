import pytest

from airlens.config import PROFILES, database_url, load_profile


@pytest.mark.parametrize("name", PROFILES)
def test_profiles_load_with_same_keys(name):
    cfg = load_profile(name)
    assert cfg["profile"] == name
    assert set(cfg) == set(load_profile("laptop"))


def test_profile_from_env(monkeypatch):
    monkeypatch.setenv("APP_PROFILE", "lab")
    assert load_profile()["profile"] == "lab"


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        load_profile("server")


def test_database_url_escapes_credentials(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "air lens")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss:w/rd")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_DB", "x_test")
    assert database_url() == "postgresql+psycopg://air+lens:p%40ss%3Aw%2Frd@db:5432/x_test"
