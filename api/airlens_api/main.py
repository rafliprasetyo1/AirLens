import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from airlens import __version__
from airlens.config import CONFIG_DIR, load_profile
from airlens.db.session import get_engine, ping
from airlens_api.iqair import IQAirClient
from airlens_api.jobs import JobStore
from airlens_api.model_store import ModelStore
from airlens_api.pipeline import PredictionPipeline
from airlens_api.pipeline import Request as PredictRequest

logger = logging.getLogger("airlens.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
PROFILE = load_profile()
# Daftar kota diverifikasi langsung ke API IQAir (lihat config/cities_id.yaml).
CITIES = yaml.safe_load((CONFIG_DIR / "cities_id.yaml").read_text(encoding="utf-8"))["cities"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    cache = Path(os.environ.get("MODEL_CACHE_DIR", "/app/modelcache"))
    models = ModelStore(cache, alias="production")
    challenger = ModelStore(cache, alias="challenger")  # shadow mode bila alias challenger ada
    models.start_background()
    challenger.start_background()
    iqair = IQAirClient(os.environ.get("IQAIR_API_KEY", ""), engine, ttl_seconds=PROFILE["iqair"]["cache_ttl_seconds"],
                        base_url=os.environ.get("IQAIR_BASE_URL", "https://api.airvisual.com/v2"))
    jobs = JobStore()
    app.state.models, app.state.challenger, app.state.iqair, app.state.jobs = models, challenger, iqair, jobs
    app.state.pipeline = PredictionPipeline(models, iqair, jobs, engine, PROFILE,
                                            Path(os.environ.get("UPLOADS_DIR", "/app/uploads")), challenger=challenger)
    app.state.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="predict")
    yield
    models.stop()
    challenger.stop()
    app.state.executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="AirLens API", version=__version__, lifespan=lifespan)


def engine_dep() -> Engine:
    return get_engine()


@app.get("/health")
def health(request: Request, engine: Engine = Depends(engine_dep)):
    model = request.app.state.models.info() if hasattr(request.app.state, "models") else {"status": "loading"}
    body = {"version": __version__, "profile": PROFILE["profile"], "model": model["status"]}
    try:
        ping(engine)
    except SQLAlchemyError as exc:
        # Jangan kirim pesan error mentah ke klien: bisa memuat host/kredensial.
        logger.warning("health: database tidak terjangkau (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "error", "db": "unreachable", **body})
    return {"status": "ok", "db": "ok", **body}


@app.get("/model")
def model_info(request: Request):
    return {**request.app.state.models.info(), "challenger": request.app.state.challenger.info()}


@app.get("/cities")
def cities():
    return [{"id": c["id"], "name": c["city"], "state": c["state"]} for c in CITIES]


@app.post("/predict", status_code=202)
async def predict(
    request: Request,
    file: UploadFile = File(...),
    city_id: str | None = Form(None),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    store_photo: bool = Form(False),
):
    """Mulai satu prediksi. Kemajuan per tahap: GET /jobs/{id}/events (SSE); hasil akhir: GET /jobs/{id}."""
    max_bytes = PROFILE["api"]["max_upload_mb"] * 2**20
    data = await file.read(max_bytes + 1)  # baca maksimal batas+1 byte; validasi menolak bila lebih
    city = None
    if city_id:
        city = next((c for c in CITIES if c["id"] == city_id), None)
        if city is None:
            raise HTTPException(status_code=422, detail="Kota tidak dikenal.")
    coords = None
    if city is None and lat is not None and lon is not None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise HTTPException(status_code=422, detail="Koordinat tidak valid.")
        coords = (lat, lon)
    job = request.app.state.jobs.create()
    req = PredictRequest(data=data, city=city, coords=coords, store_photo=store_photo)
    request.app.state.executor.submit(request.app.state.pipeline.run, job, req)
    return {"job_id": job.id, "events": f"/jobs/{job.id}/events", "result": f"/jobs/{job.id}"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str, request: Request):
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan atau sudah kedaluwarsa.")
    events, done = request.app.state.jobs.snapshot(job, 0)
    return {"job_id": job.id, "done": done, "events": events, "result": job.result}


@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    """Server-Sent Events: satu event per perubahan tahap yang sungguh terjadi di pipeline, lalu event 'hasil'."""
    jobs: JobStore = request.app.state.jobs
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan atau sudah kedaluwarsa.")

    async def stream():
        sent = 0
        while True:
            events, done = jobs.snapshot(job, sent)
            for ev in events:
                yield f"event: tahap\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            sent += len(events)
            if done:
                yield f"event: hasil\ndata: {json.dumps(job.result, ensure_ascii=False)}\n\n"
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.1)  # memeriksa event baru; bukan kemajuan buatan

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
