import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _guard_test_database():
    # Test migrasi menghapus dan membuat ulang tabel: jangan pernah jalan di database utama.
    db = os.environ.get("POSTGRES_DB", "")
    if not db.endswith("_test"):
        pytest.exit(f"POSTGRES_DB={db!r}; test hanya boleh memakai database *_test (jalankan lewat `make test`)", 2)
