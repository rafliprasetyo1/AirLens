"""Job berkala: heartbeat (cek database) dan monitoring mingguan (Fase 5).

Jadwal monitoring dari config `monitoring.schedule` (UTC). MONITOR_EVERY_MINUTES (opsional) menggantinya dengan
interval menit, untuk membuktikan job terjadwal berjalan tanpa menunggu seminggu.
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from airlens.config import load_profile
from airlens.db.session import get_engine, ping

HEARTBEAT_FILE = Path("/tmp/airlens-scheduler-heartbeat")
logger = logging.getLogger("airlens.scheduler")


def heartbeat(path: Path = HEARTBEAT_FILE) -> None:
    """Perbarui file heartbeat hanya bila database terjangkau; kalau tidak, healthcheck akan gagal."""
    ping(get_engine())
    path.write_text(str(time.time()))


def is_healthy(max_age_seconds: float, path: Path = HEARTBEAT_FILE) -> bool:
    try:
        return time.time() - float(path.read_text()) < max_age_seconds
    except (FileNotFoundError, ValueError):
        return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    cfg = load_profile()
    interval = cfg["scheduler"]["heartbeat_seconds"]
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        heartbeat, "interval", seconds=interval, id="heartbeat",
        next_run_time=datetime.now(timezone.utc), max_instances=1, coalesce=True,
    )
    every = os.environ.get("MONITOR_EVERY_MINUTES")
    trigger = (IntervalTrigger(minutes=float(every), timezone="UTC") if every
               else CronTrigger(timezone="UTC", **cfg["monitoring"]["schedule"]))
    scheduler.add_job(monitoring_job, trigger, id="monitoring", max_instances=1, coalesce=True)
    logger.info("scheduler mulai, heartbeat tiap %s detik; monitoring: %s", interval, trigger)
    scheduler.start()


def monitoring_job(report_type: str = "terjadwal") -> dict:
    from airlens.monitoring.job import run

    return run(get_engine(), load_profile(), Path(os.environ.get("MODEL_CACHE_DIR", "/app/modelcache")),
               Path(os.environ.get("AIRLENS_RESULTS_DIR", "/app/results")) / "monitoring", report_type=report_type)


if __name__ == "__main__":
    main()
