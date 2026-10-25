"""`make monitor`: jalankan job monitoring yang SAMA dengan job terjadwal, sekarang juga.

Opsi: --since/--until (ISO 8601, UTC) untuk jendela tertentu; bawaan = window_days terakhir.
"""

import argparse
import json
import logging
from datetime import datetime

from airlens_scheduler.main import monitoring_job


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--until")
    a = ap.parse_args()
    if a.since or a.until:
        from pathlib import Path
        import os

        from airlens.config import load_profile
        from airlens.db.session import get_engine
        from airlens.monitoring.job import run

        report = run(get_engine(), load_profile(), Path(os.environ.get("MODEL_CACHE_DIR", "/app/modelcache")),
                     Path(os.environ.get("AIRLENS_RESULTS_DIR", "/app/results")) / "monitoring",
                     since=datetime.fromisoformat(a.since) if a.since else None,
                     until=datetime.fromisoformat(a.until) if a.until else None, report_type="manual")
    else:
        report = monitoring_job("manual")
    print(json.dumps({k: report[k] for k in ("report_id", "n", "rejected_rate", "uncertain_rate", "alerts",
                                             "retrain_recommended", "markdown")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
