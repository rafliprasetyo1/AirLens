"""Trigger engine dua pemicu (kamera + gas) untuk semua sumber: node lengkap/simulator, Beta, kamera Beta, kamera live.

Satu aturan di config/triggers.yaml (docs/AIRLENS_KONSEP_UTAMA.md bagian 4–5):
- Pemicu kamera: masuk bila >= enter_count dari `window` penilaian smoke_prob terakhir >= enter_prob; keluar bila median
  window < exit_prob selama exit_seconds.
- Pemicu CO/VOC/NOx: masuk bila nilai >= enter `consecutive` kali berturut-turut; keluar bila < exit selama exit_seconds.
- Pemicu Beta: status alert dari api/sensor.py (sudah ber-histeresis, ambang dari bagian `beta` file yang sama).
Per ruangan: kamera + gas -> smoke_confirmed; gas -> invisible_gas; kamera -> visible_smoke; semua keluar -> back_to_normal
(sekali). Jeda anti-spam per jenis kejadian. Sumber tanpa data selama source_timeout_seconds dianggap pergi.

State pemicu disimpan di memori (satu proses uvicorn); kejadian disimpan permanen oleh `sink` (tabel events + SSE).
State hilang bila API restart; kejadian yang sudah tercatat tidak.
"""

from __future__ import annotations

import fnmatch
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

PRIORITY = {"smoke_confirmed": "high", "invisible_gas": "high", "visible_smoke": "medium", "back_to_normal": "info"}
GAS_LABEL = {"co": "CO", "voc": "VOC index", "nox": "NOx index", "beta": "MQ-2"}


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ state per pemicu (fungsi murni di dalam kelas kecil)
@dataclass
class CameraTrigger:
    cfg: dict
    probs: deque = field(default_factory=deque)
    active: bool = False
    below_since: float | None = None

    def observe(self, prob: float, now: float) -> None:
        self.probs.append(prob)
        while len(self.probs) > self.cfg["window"]:
            self.probs.popleft()
        if not self.active:
            if sum(p >= self.cfg["enter_prob"] for p in self.probs) >= self.cfg["enter_count"]:
                self.active, self.below_since = True, None
            return
        self.tick(now)

    def tick(self, now: float) -> None:
        if not self.active or not self.probs:
            return
        if statistics.median(self.probs) < self.cfg["exit_prob"]:
            self.below_since = self.below_since if self.below_since is not None else now
            if now - self.below_since >= self.cfg["exit_seconds"]:
                self.active, self.below_since = False, None
        else:
            self.below_since = None

    @property
    def value(self) -> float | None:
        return round(statistics.median(self.probs), 3) if self.probs else None


@dataclass
class GasTrigger:
    cfg: dict
    streak: int = 0
    active: bool = False
    below_since: float | None = None
    last: float | None = None
    last_at: float = 0.0

    def observe(self, value: float, now: float) -> None:
        self.last, self.last_at = value, now
        if not self.active:
            self.streak = self.streak + 1 if value >= self.cfg["enter"] else 0
            if self.streak >= self.cfg["consecutive"]:
                self.active, self.streak, self.below_since = True, 0, None
            return
        if value < self.cfg["exit"]:
            self.below_since = self.below_since if self.below_since is not None else now
        else:
            self.below_since = None
        self.tick(now)

    def tick(self, now: float) -> None:
        if self.active and self.below_since is not None and now - self.below_since >= self.cfg["exit_seconds"]:
            self.active, self.below_since = False, None


@dataclass
class Source:
    name: str
    room: str
    simulated: bool = False
    seen_at: float = 0.0
    camera: CameraTrigger | None = None
    gas: dict[str, GasTrigger] = field(default_factory=dict)
    beta_active: bool = False
    beta_ratio: float | None = None
    beta_label: str | None = None      # "smoke" | "alcohol" dari model gas Beta; None = aturan MQ-2 (tanpa model)
    beta_reason: str | None = None     # kalimat alasan dari nilai SHAP terbesar


@dataclass
class RoomState:
    current: str | None = None                 # jenis kejadian terakhir yang dikirim (None = normal)
    last_emit: dict[str, float] = field(default_factory=dict)
    last_simulated: bool = False


class TriggerEngine:
    def __init__(self, cfg: dict, sink: Callable[[dict], None] | None = None, clock: Callable[[], float] = time.time):
        self.cfg, self.sink, self.clock = cfg, sink or (lambda e: None), clock
        self.sources: dict[str, Source] = {}
        self.rooms: dict[str, RoomState] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ ruangan
    def room_of(self, source: str) -> str:
        for name, room in self.cfg["rooms"].items():
            if isinstance(room, dict) and any(fnmatch.fnmatch(source, pat) for pat in room.get("sources", [])):
                return name
        return self.cfg["rooms"]["default"]

    def _source(self, name: str, simulated: bool, now: float) -> Source:
        src = self.sources.get(name)
        if src is None:
            src = self.sources[name] = Source(name=name, room=self.room_of(name))
        src.simulated, src.seen_at = simulated, now
        return src

    # ------------------------------------------------------------------ masukan
    def observe_camera(self, source: str, smoke_prob: float, simulated: bool = False, now: float | None = None) -> list[dict]:
        now = self.clock() if now is None else now
        with self._lock:
            src = self._source(source, simulated, now)
            src.camera = src.camera or CameraTrigger(self.cfg["camera"])
            src.camera.observe(float(smoke_prob), now)
            return self._evaluate(src.room, now)

    def observe_gas(self, source: str, values: dict[str, float | None], simulated: bool = False,
                    now: float | None = None) -> list[dict]:
        """values: co (ppm), voc (indeks), nox (indeks); None = sensor tidak ada/tidak membaca."""
        now = self.clock() if now is None else now
        with self._lock:
            src = self._source(source, simulated, now)
            for metric, value in values.items():
                if value is None or metric not in ("co", "voc", "nox"):
                    continue
                src.gas.setdefault(metric, GasTrigger(self.cfg[metric])).observe(float(value), now)
            return self._evaluate(src.room, now)

    def observe_beta(self, source: str, alert: bool, ratio: float | None, simulated: bool = False,
                     now: float | None = None, label: str | None = None, reason: str | None = None) -> list[dict]:
        """Status Beta yang sudah ber-histeresis (api/sensor.py). label/reason dari model gas Beta bila ada."""
        now = self.clock() if now is None else now
        with self._lock:
            src = self._source(source, simulated, now)
            src.beta_active, src.beta_ratio = bool(alert), ratio
            src.beta_label, src.beta_reason = (label, reason) if alert else (None, None)
            return self._evaluate(src.room, now)

    def tick(self, now: float | None = None) -> list[dict]:
        """Dipanggil berkala: pemicu yang keluar karena waktu, dan sumber yang sudah pergi."""
        now = self.clock() if now is None else now
        with self._lock:
            timeout = self.cfg["source_timeout_seconds"]
            for name in [n for n, s in self.sources.items() if now - s.seen_at > timeout]:
                del self.sources[name]
            for src in self.sources.values():
                if src.camera:
                    src.camera.tick(now)
                for g in src.gas.values():
                    g.tick(now)
            events = []
            for room in {*(s.room for s in self.sources.values()), *self.rooms}:
                events += self._evaluate(room, now)
            return events

    # ------------------------------------------------------------------ keputusan per ruangan
    def snapshot(self, room: str) -> dict:
        with self._lock:
            cam, gas, sim = self._active(room)
            return {"room": room, "camera": bool(cam), "gas": bool(gas), "current": self.rooms.get(room, RoomState()).current,
                    "sources": sorted({s for s, *_ in cam} | {s for s, *_ in gas}), "simulated": sim}

    def _active(self, room: str):
        cam, gas, sim = [], [], False
        for s in self.sources.values():
            if s.room != room:
                continue
            if s.camera and s.camera.active:
                cam.append((s.name, s.camera.value))
                sim |= s.simulated
            for metric, g in s.gas.items():
                if g.active:
                    gas.append((s.name, metric, g.last))
                    sim |= s.simulated
            if s.beta_active:
                gas.append((s.name, "beta", s.beta_ratio))
                sim |= s.simulated
        return cam, gas, sim

    def _evaluate(self, room: str, now: float) -> list[dict]:
        state = self.rooms.setdefault(room, RoomState())
        cam, gas, sim = self._active(room)
        kind = "smoke_confirmed" if cam and gas else "invisible_gas" if gas else "visible_smoke" if cam else None
        if kind is None:
            if state.current is None:
                return []
            event = self._event(room, "back_to_normal", [], [], state.last_simulated, now)
            state.current = None
            return [event]
        if kind == state.current or now - state.last_emit.get(kind, -1e18) < self.cfg["cooldown_seconds"]:
            return []
        # Saat mereda, kamera dan gas keluar pada waktu berbeda (kamera 30 s, gas 60 s). Smoke confirmed tidak
        # "turun" ke salah satunya: tetap berlaku sampai semua pemicu keluar, lalu ditutup satu back_to_normal.
        if state.current == "smoke_confirmed":
            return []
        state.current, state.last_simulated = kind, sim
        state.last_emit[kind] = now
        return [self._event(room, kind, cam, gas, sim, now)]

    def _event(self, room: str, kind: str, cam: list, gas: list, simulated: bool, now: float) -> dict:
        values = {}
        for name, prob in cam:
            values[f"{name}.smoke_prob_median"] = prob
        for name, metric, value in gas:
            values[f"{name}.{'mq2_ratio' if metric == 'beta' else metric}"] = round(value, 3) if value is not None else None
        beta = [(s.beta_label, s.beta_reason) for s in self.sources.values()
                if s.room == room and s.beta_active and s.name in {g[0] for g in gas}]
        for name, metric, _ in gas:
            if metric == "beta" and self.sources[name].beta_label:
                values[f"{name}.beta_class"] = self.sources[name].beta_label
        event = {"room": room, "kind": kind, "priority": PRIORITY[kind], "message": message(kind, cam, gas, beta),
                 "sources": sorted({c[0] for c in cam} | {g[0] for g in gas}), "trigger_values": values,
                 "simulated": simulated, "at": now}
        self.sink(event)
        return event


def message(kind: str, cam: list, gas: list, beta: list | None = None) -> str:
    """Teks kejadian (dokumen konsep §4). Sumber disebut, mis. 'Camera + gas sensor agree'.
    beta: [(label, kalimat alasan SHAP)] dari node Beta yang aktif; alasan pertama ditempel ke pesan."""
    metrics = {m for _, m, _ in gas}
    reason = next((r for _, r in (beta or []) if r), None)
    labels = {lbl for lbl, _ in (beta or []) if lbl}
    if kind == "smoke_confirmed":
        text = "Smoke confirmed: camera and gas sensor agree"
        return f"{text}. {reason}" if reason else text
    if kind == "invisible_gas":
        if "co" in metrics:
            return "Invisible gas detected, likely CO. Ventilate now"
        if metrics & {"voc", "nox"}:
            return "Gas detected (" + ", ".join(GAS_LABEL[m] for m in sorted(metrics & {"voc", "nox"})) + ")"
        if labels:
            head = "Possible local smoke (Beta)" if "smoke" in labels else "Alcohol/VOC detected (Beta)"
            return f"{head}. {reason}" if reason else head
        return "Possible local smoke or gas (MQ-2)"
    if kind == "visible_smoke":
        return "Visible smoke, check the room"
    return "Back to normal"
