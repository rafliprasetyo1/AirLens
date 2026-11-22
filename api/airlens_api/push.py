"""Notifikasi kejadian: teks notifikasi (satu sumber untuk halaman dan Web Push) + Web Push saat website tertutup.

Sumber kejadian tetap satu: trigger engine (EventHub.sink). Untuk setiap kejadian baru:
- `notification(event)` membuat judul, isi, URL tujuan, dan tag. Halaman (lewat SSE) dan push memakai teks yang
  sama, dan tag yang sama (`airlens-event-<id>`) sehingga notifikasi ganda (halaman + push) digabung oleh sistem.
- `PushSender.send_event` mengirim ke semua subscription di thread latar (trigger engine tidak menunggu jaringan).
  Respons 404/410 = subscription kedaluwarsa -> dihapus otomatis.
Anti-spam berasal dari trigger engine (cooldown 60 s, satu Back to normal); modul ini tidak menambah aturan sendiri.
Privasi: hanya subscription push yang disimpan (endpoint + kunci browser), tanpa data pribadi lain.

Kunci VAPID dibuat `make vapid-keys` (python -m airlens_api.push generate) dan disimpan di .env, tidak di repo.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from airlens.db.models import PushSubscription
from airlens.db.session import get_engine

logger = logging.getLogger("airlens.api.push")
router = APIRouter(prefix="/push", tags=["push"])

TITLES = {"smoke_confirmed": "Smoke confirmed", "invisible_gas": "Invisible gas detected",
          "visible_smoke": "Visible smoke", "back_to_normal": "Back to normal"}
ADVICE = {"smoke_confirmed": "Ventilate and leave the area if the smoke grows.",
          "invisible_gas": "Open the windows and ventilate now.",
          "visible_smoke": "Check the room for a source of smoke.",
          "back_to_normal": "All triggers have cleared."}


def notification(event: dict) -> dict:
    """Judul, isi, URL, tag notifikasi untuk satu kejadian (dict dari events.to_dict)."""
    kind, sources = event["kind"], event.get("sources") or []
    beta_only = bool(sources) and all(s.startswith("beta:") for s in sources)
    title = TITLES.get(kind, kind)
    if kind == "invisible_gas" and beta_only and "Alcohol" not in event.get("message", ""):
        title = "Possible local smoke or gas"
    if kind == "invisible_gas" and "Alcohol" in event.get("message", ""):
        title = "Alcohol or VOC detected"
    if event.get("simulated"):
        title = f"[Simulated] {title}"
    values = event.get("trigger_values") or {}
    shown = [f"{k.split('.', 1)[1]} {v}" for k, v in values.items() if isinstance(v, (int, float))][:3]
    parts = [event.get("message", "")]
    if sources:
        parts.append("Source: " + ", ".join(sources))
    if shown:
        parts.append("Values: " + ", ".join(shown))
    parts.append(ADVICE.get(kind, ""))
    url = "/beta.html"
    return {"title": title, "body": "\n".join(p for p in parts if p), "url": url,
            "tag": f"airlens-event-{event.get('id')}", "kind": kind, "priority": event.get("priority"),
            "simulated": bool(event.get("simulated"))}


# ------------------------------------------------------------------ kirim
class PushSender:
    def __init__(self, public_key: str | None = None, private_key: str | None = None, subject: str | None = None,
                 webpush=None, workers: int = 2):
        self.public_key = public_key if public_key is not None else os.environ.get("VAPID_PUBLIC_KEY", "")
        self.private_key = private_key if private_key is not None else os.environ.get("VAPID_PRIVATE_KEY", "")
        self.subject = subject or os.environ.get("VAPID_SUBJECT", "") or "mailto:airlens@example.com"
        self._webpush = webpush
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="push")
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.public_key and self.private_key)

    def _send_one(self, sub: PushSubscription, payload: str) -> str:
        webpush = self._webpush
        if webpush is None:
            from pywebpush import webpush
        try:
            webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                    data=payload, vapid_private_key=self.private_key, vapid_claims={"sub": self.subject}, ttl=300)
            return "ok"
        except Exception as exc:   # WebPushException membawa response; 404/410 = kedaluwarsa
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                return "gone"
            logger.warning("push gagal (%s): %s", status, type(exc).__name__)
            return "error"

    def send_event(self, event: dict, wait: bool = False) -> dict:
        """Kirim push untuk satu kejadian ke semua subscription. wait=True dipakai tes."""
        if not self.enabled:
            return {"sent": 0, "removed": 0, "skipped": "VAPID belum diatur"}
        fut = self._pool.submit(self._send_all, notification(event))
        return fut.result() if wait else {"queued": True}

    def _send_all(self, note: dict) -> dict:
        payload = json.dumps(note)
        engine = get_engine()
        with Session(engine) as s:
            subs = s.scalars(select(PushSubscription)).all()
            results = {sub.id: self._send_one(sub, payload) for sub in subs}
            gone = [i for i, r in results.items() if r == "gone"]
            if gone:
                s.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
            now = datetime.now(timezone.utc)
            for sub in subs:
                if results[sub.id] == "ok":
                    sub.last_ok_at = now
            s.commit()
        out = {"sent": sum(r == "ok" for r in results.values()), "removed": len(gone),
               "errors": sum(r == "error" for r in results.values())}
        logger.info("push %s: %s", note["kind"], out)
        return out


# ------------------------------------------------------------------ endpoint subscription
class Keys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=20, max_length=1000, pattern=r"^https://")
    keys: Keys


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=20, max_length=1000)


@router.get("/public-key")
def public_key(request: Request):
    sender: PushSender = request.app.state.push
    if not sender.enabled:
        raise HTTPException(status_code=404, detail="Web Push belum diatur (make vapid-keys).")
    return {"public_key": sender.public_key}


@router.post("/subscribe")
def subscribe(body: SubscriptionIn):
    with Session(get_engine()) as s:
        s.execute(insert(PushSubscription).values(endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth)
                  .on_conflict_do_update(index_elements=["endpoint"],
                                         set_={"p256dh": body.keys.p256dh, "auth": body.keys.auth}))
        s.commit()
    return {"subscribed": True}


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeIn):
    with Session(get_engine()) as s:
        n = s.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint)).rowcount
        s.commit()
    return {"removed": n}


# ------------------------------------------------------------------ kunci VAPID
def generate_keys() -> tuple[str, str]:
    """Pasangan kunci VAPID (P-256) dalam format base64url yang dipakai browser dan pywebpush."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    raw_pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    raw_priv = key.private_numbers().private_value.to_bytes(32, "big")
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    return b64(raw_pub), b64(raw_priv)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "generate":
    pub, priv = generate_keys()
    print(f"VAPID_PUBLIC_KEY={pub}\nVAPID_PRIVATE_KEY={priv}")
