"""Kejadian trigger engine: simpan ke tabel events, siarkan ke pendengar SSE, dan endpoint baca.

Masukan trigger engine datang dari endpoint sinkron (thread pool), sedangkan SSE berjalan di event loop asyncio. Siaran
memakai `loop.call_soon_threadsafe` ke antrean tiap pendengar. Satu proses uvicorn (workers=1), jadi siaran di memori
cukup; dicatat di DECISIONS.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from airlens.db.models import Event
from airlens.db.session import get_engine

logger = logging.getLogger("airlens.api.events")
router = APIRouter(tags=["events"])


def to_dict(row: Event) -> dict:
    out = {"id": row.id, "at": row.created_at.isoformat(), "room": row.room, "kind": row.kind,
           "priority": row.priority, "message": row.message, "sources": row.sources or [],
           "trigger_values": row.trigger_values or {}, "simulated": row.simulated}
    from airlens_api.push import notification

    out["notification"] = notification(out)   # teks notifikasi yang sama untuk halaman dan Web Push
    return out


class EventHub:
    def __init__(self, push=None):
        self.loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self.push = push   # PushSender (Web Push), dipasang di main.py

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def sink(self, event: dict) -> None:
        """Dipanggil trigger engine untuk setiap kejadian baru: simpan, lalu siarkan."""
        with Session(get_engine()) as s:
            row = Event(created_at=datetime.fromtimestamp(event["at"], tz=timezone.utc), room=event["room"],
                        kind=event["kind"], priority=event["priority"], message=event["message"],
                        sources=event["sources"], trigger_values=event["trigger_values"], simulated=event["simulated"])
            s.add(row)
            s.commit()
            s.refresh(row)
            payload = to_dict(row)
        if self.push is not None:   # Web Push (thread latar); halaman yang terbuka menerima lewat SSE
            try:
                self.push.send_event(payload)
            except Exception:
                logger.exception("antrian push gagal; kejadian tetap tersimpan dan disiarkan")
        logger.info("kejadian %s di %s (%s)%s", payload["kind"], payload["room"], ", ".join(payload["sources"]),
                    " [Simulated]" if payload["simulated"] else "")
        with self._lock:
            queues, loop = list(self._queues), self.loop
        if loop is None:
            return
        for q in queues:
            loop.call_soon_threadsafe(self._offer, q, payload)

    @staticmethod
    def _offer(q: asyncio.Queue, payload: dict) -> None:
        if q.full():          # pendengar lambat: buang yang tertua daripada menahan semua
            q.get_nowait()
        q.put_nowait(payload)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        with self._lock:
            self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._queues.discard(q)


@router.get("/events/latest")
def latest(request: Request, room: str = Query("booth", max_length=64)):
    with Session(get_engine()) as s:
        row = s.scalars(select(Event).where(Event.room == room).order_by(Event.created_at.desc(), Event.id.desc())
                        .limit(1)).first()
    return {"event": to_dict(row) if row else None, "state": request.app.state.triggers.snapshot(room)}


@router.get("/events")
def recent(room: str | None = Query(None, max_length=64), minutes: int = Query(60, ge=1, le=24 * 60)):
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with Session(get_engine()) as s:
        q = select(Event).where(Event.created_at >= since)
        if room:
            q = q.where(Event.room == room)
        rows = s.scalars(q.order_by(Event.created_at.desc(), Event.id.desc()).limit(500)).all()
    return {"events": [to_dict(r) for r in rows]}


@router.get("/events/stream")
async def stream(request: Request, room: str | None = Query(None, max_length=64)):
    """Server-Sent Events: satu pesan `event: kejadian` per kejadian baru; komentar keepalive tiap 15 detik."""
    hub: EventHub = request.app.state.event_hub
    if hub.loop is None:
        raise HTTPException(status_code=503, detail="Aliran kejadian belum siap.")
    q = hub.subscribe()

    async def gen():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        return
                    yield ": keepalive\n\n"
                    continue
                if room and ev["room"] != room:
                    continue
                yield f"event: kejadian\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def tick_forever(app, every: float = 5.0) -> None:
    """Pemicu yang keluar karena waktu dan sumber yang pergi tetap diproses walau tidak ada data baru."""
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(every)
        try:
            await loop.run_in_executor(None, app.state.triggers.tick)
        except Exception:
            logger.exception("tick trigger engine gagal")
