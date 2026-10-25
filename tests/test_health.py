from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from airlens_api.main import app, engine_dep


def test_health_ok():
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["db"] == "ok"


def test_health_reports_unreachable_db_without_leaking_details():
    secret = "rahasia-jangan-bocor"
    dead = create_engine(
        f"postgresql+psycopg://airlens:{secret}@127.0.0.1:1/nowhere", connect_args={"connect_timeout": 1}
    )
    app.dependency_overrides[engine_dep] = lambda: dead
    try:
        with TestClient(app) as client:
            r = client.get("/health")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json()["db"] == "unreachable"
    assert secret not in r.text and "127.0.0.1" not in r.text
