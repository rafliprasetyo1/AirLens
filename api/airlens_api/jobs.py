"""Job prediksi di memori: tiap job punya daftar event tahap yang dikirim ke frontend lewat SSE.

Event dibuat saat tahap benar-benar dimulai/selesai di pipeline (tidak ada timer palsu). Job lama dibersihkan
setelah JOB_TTL. Satu proses uvicorn (workers=1), jadi penyimpanan di memori cukup; dicatat di DECISIONS.md.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field

JOB_TTL = 3600.0


@dataclass
class Job:
    id: str
    created: float
    events: list[dict] = field(default_factory=list)
    done: bool = False
    result: dict | None = None


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(id=str(uuid.uuid4()), created=time.time())
        with self._lock:
            now = time.time()
            for jid in [j for j, v in self._jobs.items() if now - v.created > JOB_TTL]:
                del self._jobs[jid]
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def emit(self, job: Job, stage: str, status: str, **extra) -> None:
        with self._lock:
            job.events.append({"stage": stage, "status": status, "t": round(time.time() - job.created, 3), **extra})

    def finish(self, job: Job, result: dict) -> None:
        with self._lock:
            job.result = result
            job.events.append({"stage": "selesai", "status": result["status"], "t": round(time.time() - job.created, 3)})
            job.done = True

    def snapshot(self, job: Job, start: int) -> tuple[list[dict], bool]:
        with self._lock:
            return list(job.events[start:]), job.done
