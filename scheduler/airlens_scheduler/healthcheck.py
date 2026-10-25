"""Dipakai healthcheck docker: sehat bila heartbeat lebih baru dari 3x interval."""

import sys

from airlens.config import load_profile
from airlens_scheduler.main import is_healthy

sys.exit(0 if is_healthy(3 * load_profile()["scheduler"]["heartbeat_seconds"]) else 1)
