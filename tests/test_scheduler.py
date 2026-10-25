import time

from airlens_scheduler.main import heartbeat, is_healthy


def test_heartbeat_writes_fresh_timestamp(tmp_path):
    hb = tmp_path / "hb"
    heartbeat(hb)
    assert is_healthy(60, hb)


def test_stale_or_missing_heartbeat_is_unhealthy(tmp_path):
    hb = tmp_path / "hb"
    assert not is_healthy(60, hb)
    hb.write_text(str(time.time() - 600))
    assert not is_healthy(60, hb)
