"""Node lengkap (konsep: Raspberry Pi 5 + SEN66 + CO-B4 + kamera) dan simulatornya. Lewat nginx: /api/node/...

Skema persis hardware/README.md. Node hanya mengirim angka; keputusan diambil trigger engine (config/triggers.yaml):
smoke_prob -> pemicu kamera node:<id>; co_ppm, voc_index, nox_index -> pemicu gas node:<id>.
Token: bila NODE_TOKEN di .env terisi, POST wajib membawa header X-Node-Token yang sama.
"""

import hmac
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from airlens.db.models import NodeReading
from airlens.db.session import get_engine

router = APIRouter(prefix="/node", tags=["node"])
NODE_ID = r"^[A-Za-z0-9_.-]{1,64}$"
OFFLINE_SECONDS = 20
FIELDS = ("smoke_prob", "co_ppm", "pm25", "pm10", "co2_ppm", "voc_index", "nox_index", "temp_c", "rh")


def _num(lo: float, hi: float, required: bool = False):
    return Field(... if required else None, ge=lo, le=hi, allow_inf_nan=False)


class NodeReadingIn(BaseModel):
    """Rentang wajar per besaran; nilai di luar rentang ditolak (422), bukan dipotong."""
    node_id: str = Field(pattern=NODE_ID)
    uptime_s: int | None = Field(default=None, ge=0)
    smoke_prob: float = _num(0, 1, required=True)      # model asap di alat (ONNX/HEF)
    co_ppm: float | None = _num(0, 1000)               # CO-B4 setelah kalibrasi; None bila sel belum siap
    pm25: float | None = _num(0, 1000)
    pm10: float | None = _num(0, 1000)
    co2_ppm: float | None = _num(0, 40000)
    voc_index: float | None = _num(1, 500)             # indeks Sensirion, bukan ppm
    nox_index: float | None = _num(1, 500)             # indeks Sensirion, bukan ppm
    temp_c: float | None = _num(-40, 85)
    rh: float | None = _num(0, 100)
    simulated: bool = False                            # hanya dikirim scripts/node_sim.py


def require_token(x_node_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("NODE_TOKEN", "")
    # Mode expo (semua endpoint publik lewat ngrok): token WAJIB. Tanpa token yang diatur, semua kiriman ditolak.
    if not expected and os.environ.get("EXPO_MODE", "0") == "1":
        raise HTTPException(status_code=503, detail="NODE_TOKEN wajib diisi di mode expo (make tokens, lalu make up).")
    if expected and not hmac.compare_digest((x_node_token or "").encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Token node salah atau tidak ada (header X-Node-Token).")


def _row(r: NodeReading) -> dict:
    return {"t": r.received_at.isoformat(), **{f: getattr(r, f) for f in FIELDS}}


@router.post("/readings", dependencies=[Depends(require_token)])
def post_reading(body: NodeReadingIn, request: Request):
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        s.add(NodeReading(node_id=body.node_id, received_at=now, uptime_s=body.uptime_s, simulated=body.simulated,
                          **{f: getattr(body, f) for f in FIELDS}))
        s.commit()
    triggers = request.app.state.triggers
    source = f"node:{body.node_id}"
    events = triggers.observe_camera(source, body.smoke_prob, body.simulated)
    events += triggers.observe_gas(source, {"co": body.co_ppm, "voc": body.voc_index, "nox": body.nox_index},
                                   body.simulated)
    return {"accepted": True, "node_id": body.node_id, "events": [e["kind"] for e in events]}


@router.get("/latest")
def get_latest(node_id: str = Query(pattern=NODE_ID)):
    with Session(get_engine()) as s:
        r = s.scalars(select(NodeReading).where(NodeReading.node_id == node_id)
                      .order_by(NodeReading.received_at.desc(), NodeReading.id.desc()).limit(1)).first()
    if r is None:
        raise HTTPException(status_code=404, detail="Node belum pernah mengirim data.")
    age = (datetime.now(timezone.utc) - r.received_at).total_seconds()
    return {"node_id": node_id, "online": age <= OFFLINE_SECONDS, "seconds_since": round(age, 1),
            "simulated": r.simulated, "reading": _row(r)}


@router.get("/history")
def get_history(node_id: str = Query(pattern=NODE_ID), minutes: int = Query(30, ge=1, le=120)):
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with Session(get_engine()) as s:
        rows = s.scalars(select(NodeReading).where(NodeReading.node_id == node_id, NodeReading.received_at >= since)
                         .order_by(NodeReading.received_at, NodeReading.id)).all()
    return {"node_id": node_id, "readings": [_row(r) for r in rows]}
