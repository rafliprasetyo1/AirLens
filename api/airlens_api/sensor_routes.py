"""Endpoint sensor Beta. Lewat nginx menjadi /api/sensor/...

Token: bila SENSOR_TOKEN di .env terisi, POST /sensor/readings dan POST /sensor/baseline/reset wajib membawa header
X-Node-Token yang sama. Bila kosong, keduanya diterima tanpa token (jaringan booth tertutup). Endpoint baca (GET)
selalu terbuka karena dipakai halaman Beta.
"""

import hmac
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from airlens.db.session import get_engine
from airlens_api import sensor

router = APIRouter(prefix="/sensor", tags=["sensor"])
NODE_ID = r"^[A-Za-z0-9_.-]{1,64}$"


def _mv():
    return Field(default=None, ge=0, le=5000, allow_inf_nan=False)


class ReadingIn(BaseModel):
    """Format 4 MQ (revisi Beta SHAP): mq2_mv, mq3_mv, mq7_mv, mq135_mv = tegangan pin ADC ESP32 (mV, setelah pembagi).
    Format lama (satu MQ-2): mq2_rs_kohm. Salah satu harus lengkap; keduanya sekaligus ditolak."""
    node_id: str = Field(pattern=NODE_ID)
    mq2_rs_kohm: float | None = Field(default=None, allow_inf_nan=False)  # -1 = kabel lepas (disimpan, tidak valid)
    mq2_mv: float | None = _mv()
    mq3_mv: float | None = _mv()
    mq7_mv: float | None = _mv()
    mq135_mv: float | None = _mv()
    uptime_s: int | None = Field(default=None, ge=0)
    simulated: bool = False  # hanya dikirim simulator; ESP32 tidak mengirim field ini

    @model_validator(mode="after")
    def one_format(self):
        mv = [self.mq2_mv, self.mq3_mv, self.mq7_mv, self.mq135_mv]
        if self.mq2_rs_kohm is not None and any(v is not None for v in mv):
            raise ValueError("kirim format lama (mq2_rs_kohm) ATAU format 4 MQ (mq*_mv), bukan keduanya")
        if self.mq2_rs_kohm is None and not all(v is not None for v in mv):
            raise ValueError("format 4 MQ butuh mq2_mv, mq3_mv, mq7_mv, dan mq135_mv")
        return self

    def mv(self) -> dict[str, float] | None:
        if self.mq2_rs_kohm is not None:
            return None
        return {"MQ2": self.mq2_mv, "MQ3": self.mq3_mv, "MQ7": self.mq7_mv, "MQ135": self.mq135_mv}


class ResetIn(BaseModel):
    node_id: str = Field(pattern=NODE_ID)


def require_token(x_node_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("SENSOR_TOKEN", "")
    # Mode expo (semua endpoint publik lewat ngrok): token WAJIB. Tanpa token yang diatur, semua kiriman ditolak.
    if not expected and os.environ.get("EXPO_MODE", "0") == "1":
        raise HTTPException(status_code=503, detail="SENSOR_TOKEN wajib diisi di mode expo (make tokens, lalu make up).")
    if expected and not hmac.compare_digest((x_node_token or "").encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Token node salah atau tidak ada (header X-Node-Token).")


def _cfg(request: Request) -> sensor.SensorConfig:
    return request.app.state.sensor_cfg


@router.post("/readings", dependencies=[Depends(require_token)])
def post_reading(body: ReadingIn, request: Request):
    st = request.app.state
    result = sensor.record_reading(get_engine(), _cfg(request), body.node_id, body.mq2_rs_kohm, body.uptime_s,
                                   body.simulated, mv=body.mv(), model=getattr(st, "beta_model", None),
                                   challenger=getattr(st, "beta_challenger", None))
    # Pemicu gas Beta masuk ke trigger engine (status alert sudah ber-histeresis di atas), beserta label model
    # ("smoke"/"alcohol") dan kalimat alasan SHAP untuk notifikasi.
    st.triggers.observe_beta(f"beta:{body.node_id}", result["state"] == "alert", result["ratio"], body.simulated,
                             label=result.get("label"), reason=result.get("reason"))
    return result


@router.get("/latest")
def get_latest(request: Request, node_id: str = Query(pattern=NODE_ID)):
    body = sensor.latest(get_engine(), _cfg(request), node_id)
    if body is None:
        raise HTTPException(status_code=404, detail="Node belum pernah mengirim data.")
    return body


@router.get("/history")
def get_history(request: Request, node_id: str = Query(pattern=NODE_ID), minutes: int = Query(30, ge=1),
                since: datetime | None = Query(None)):
    """since (ISO 8601) = hanya bacaan setelah waktu itu; halaman Beta memakainya agar tidak mengunduh ulang 30 menit."""
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return {"node_id": node_id, "readings": sensor.history(get_engine(), _cfg(request), node_id, minutes, since=since)}


@router.get("/nodes")
def get_nodes(request: Request):
    return sensor.nodes(get_engine(), _cfg(request))


@router.post("/baseline/reset", dependencies=[Depends(require_token)])
def post_reset(body: ResetIn):
    if not sensor.reset_baseline(get_engine(), body.node_id):
        raise HTTPException(status_code=404, detail="Node belum pernah mengirim data.")
    return {"node_id": body.node_id, "state": "warming_up"}


# ------------------------------------------------------------------ revisi Beta SHAP: penjelasan dan model
@router.get("/explain/latest")
def get_explain_latest(node_id: str = Query(pattern=NODE_ID)):
    body = sensor.explain_latest(get_engine(), node_id)
    if body is None:
        raise HTTPException(status_code=404, detail="Node belum pernah mengirim data.")
    return body


@router.get("/model")
def get_model(request: Request):
    store = getattr(request.app.state, "beta_model", None)
    if store is None:
        return {"status": "unavailable", "available": False}
    return {**store.summary(), "available": store.status == "ok",
            "challenger": getattr(request.app.state, "beta_challenger", None) and request.app.state.beta_challenger.info()}


PLOTS = {"shap_bar.png", "shap_beeswarm_smoke.png", "confusion_test.png"}


@router.get("/model/plots/{name}")
def get_model_plot(name: str, request: Request):
    store = getattr(request.app.state, "beta_model", None)
    path = store.plot_path(name) if store is not None and name in PLOTS else None
    if path is None:
        raise HTTPException(status_code=404, detail="Plot belum tersedia.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=300"})


# Alias sesuai docs/prompts/6_beta_shap.md: /api/beta/explain/latest dan /api/beta/model (sama persis dengan /sensor/...).
beta_router = APIRouter(prefix="/beta", tags=["sensor"])
beta_router.add_api_route("/explain/latest", get_explain_latest, methods=["GET"])
beta_router.add_api_route("/model", get_model, methods=["GET"])
beta_router.add_api_route("/model/plots/{name}", get_model_plot, methods=["GET"])
