"""Pembanding zero-shot Qwen2.5-VL lewat LM Studio (endpoint OpenAI-compatible). OPSIONAL.

Jalur utama tidak pernah bergantung pada modul ini. Bila VLM_BASE_URL kosong, tidak terjangkau, atau tidak ada model
vision-language yang termuat, hasilnya berstatus "dilewati" beserta alasannya, bukan error.
Keluaran dipaksa JSON (json_schema), temperature 0.
"""

import base64
import io
import json
import logging
import os
import time

import requests
from PIL import Image

from airlens.aqi import CATEGORY_LABELS
from airlens.models.preprocess import load_image

logger = logging.getLogger("airlens.models.vlm")
VL_HINTS = ("vl", "vision", "llava", "qwen2.5-omni")
TIMEOUT = 120


def _schema(classes: list[str]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "aqi_category",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"category": {"type": "string", "enum": classes}, "reason": {"type": "string"}},
                "required": ["category", "reason"],
                "additionalProperties": False,
            },
        },
    }


def _prompt(classes: list[str]) -> str:
    opts = "; ".join(f"{c} = {CATEGORY_LABELS.get(c, c)}" for c in classes)
    return (
        "Estimate the US EPA air quality category (PM2.5) visible in this outdoor photo, judging haze, visibility, "
        f"sky color and contrast. Choose exactly one category from: {opts}. "
        "Answer only with JSON: {\"category\": ..., \"reason\": <one short sentence>}."
    )


def find_model(base_url: str, wanted: str | None) -> tuple[str | None, str]:
    """(model_id, alasan). model_id None berarti dilewati."""
    if not base_url:
        return None, "VLM_BASE_URL kosong"
    try:
        r = requests.get(f"{base_url.rstrip('/')}/models", timeout=5)
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", [])]
    except (requests.RequestException, ValueError, KeyError) as exc:
        return None, f"LM Studio tidak terjangkau di {base_url} ({type(exc).__name__})"
    if wanted:
        return (wanted, "ok") if wanted in ids else (None, f"VLM_MODEL={wanted} tidak termuat (tersedia: {ids})")
    vl = [i for i in ids if any(h in i.lower() for h in VL_HINTS)]
    if not vl:
        return None, f"tidak ada model vision-language yang termuat (tersedia: {ids})"
    return vl[0], "ok"


def _encode(path: str, max_side: int = 768) -> str:
    img = load_image(path, size=max_side // 2)
    img.thumbnail((max_side, max_side), Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def parse_category(text: str, classes: list[str]) -> str | None:
    try:
        cat = json.loads(text).get("category")
    except (json.JSONDecodeError, AttributeError):
        return None
    return cat if cat in classes else None


def classify(paths: list[str], classes: list[str], base_url: str | None = None, model: str | None = None) -> dict:
    """{"status": "ok"|"dilewati", "reason", "model", "predictions": [kelas atau None], "seconds": [...]}."""
    base_url = base_url if base_url is not None else os.environ.get("VLM_BASE_URL", "")
    model_id, reason = find_model(base_url, model if model is not None else os.environ.get("VLM_MODEL") or None)
    if model_id is None:
        logger.warning("pembanding VLM dilewati: %s", reason)
        return {"status": "dilewati", "reason": reason, "model": None, "predictions": [], "seconds": []}

    url = f"{base_url.rstrip('/')}/chat/completions"
    preds, secs = [], []
    for p in paths:
        body = {
            "model": model_id,
            "temperature": 0,
            "response_format": _schema(classes),
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": _prompt(classes)},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_encode(p)}"}},
            ]}],
        }
        start = time.perf_counter()
        try:
            r = requests.post(url, json=body, timeout=TIMEOUT)
            r.raise_for_status()
            preds.append(parse_category(r.json()["choices"][0]["message"]["content"], classes))
        except (requests.RequestException, KeyError, ValueError) as exc:
            logger.warning("VLM gagal untuk %s: %s", p, type(exc).__name__)
            preds.append(None)
        secs.append(time.perf_counter() - start)
    return {"status": "ok", "reason": "ok", "model": model_id, "predictions": preds, "seconds": secs}
