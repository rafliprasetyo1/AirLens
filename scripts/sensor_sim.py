#!/usr/bin/env python3
"""Simulator node Beta: mengirim data seperti ESP32 + MQ-2 ke AirLens, berlabel simulated.

Dipakai untuk menguji dan mendemokan halaman Beta tanpa perangkat (atau sebagai cadangan di booth bila node rusak).
Hanya memakai pustaka standar Python, jadi bisa dijalankan langsung di host:

    python3 scripts/sensor_sim.py                       # ke http://localhost:8080/api/sensor/readings
    python3 scripts/sensor_sim.py --url http://192.168.43.25:8080/api/sensor/readings

Bentuk sinyal: Rs udara bersih ±18 kΩ dengan derau kecil dan drift lambat. Lonjakan asap pertama setelah
pemanasan + pengumpulan baseline di server (180 s + 24 × 5 s), lalu berulang: Rs turun ke ±40% (rasio < 0,6 →
Alert), bertahan, lalu pulih (rasio > 0,8 → Normal). Bila SENSOR_TOKEN ada di environment, dikirim sebagai
header X-Node-Token. Data selalu membawa "simulated": true sehingga halaman memberi label "Simulated".

Mode replay (revisi Beta SHAP, format 4 MQ):

    python3 scripts/sensor_sim.py --replay dataset          # butuh `make data-beta` (CSV MultimodalGasData)

Memutar ulang baris MultimodalGasData per kelas setiap 2 detik: udara bersih selama pemanasan + pengumpulan baseline
(--warmup, bawaan 240 s), lalu bergiliran clean -> smoke -> clean -> alcohol -> clean -> mixture (--phase, bawaan
60 s). Konversi nilai dataset ke mV pin ESP32: rasio tiap sensor terhadap median NoGas dataset dianggap = Rs/R0 alat
(arahnya sama: turun saat ada gas). Dengan R0 dari tegangan udara bersih pilihan (MQ-2 900 mV, MQ-3 800, MQ-7 1000,
MQ-135 850; RL 1 kΩ, Vc 5 V, pembagi 10k/20k), Rs = rasio × R0, lalu Vout = Vc·RL/(RL+Rs) dan pin = Vout / 1,5.
Server menghitung balik Rs dari mV, sehingga fitur yang sampai ke model sama dengan rasio dataset.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request



def env_token(name: str) -> str:
    """Token dari environment, atau dari .env repo (mode expo mewajibkan token; simulator tetap satu perintah)."""
    v = os.environ.get(name, "")
    if v:
        return v
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    try:
        for line in open(env, encoding="utf-8"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""

def spike_factor(t: float, first: float, every: float, length: float, depth: float = 0.4) -> float:
    """Pengali Rs pada detik t (1 = udara bersih). Lonjakan: turun 8 s, bertahan, pulih eksponensial."""
    if t < first:
        return 1.0
    tau = (t - first) % every
    if tau >= length + 30:  # pulih penuh sebelum lonjakan berikutnya
        return 1.0
    if tau < 8:
        return 1 - (1 - depth) * (tau / 8)
    if tau < length:
        return depth
    return 1 - (1 - depth) * math.exp(-(tau - length) / 6)


def rs_at(t: float, rng: random.Random, base: float = 18.0, first: float = 360, every: float = 240,
          length: float = 45) -> float:
    drift = 1 + 0.03 * math.sin(2 * math.pi * t / 900)
    noise = 1 + rng.gauss(0, 0.015)
    return round(base * drift * spike_factor(t, first, every, length) * noise, 2)


# ------------------------------------------------------------------ replay dataset (format 4 MQ)
SENSORS = ("MQ2", "MQ3", "MQ7", "MQ135")
CLEAN_PIN_MV = {"MQ2": 900.0, "MQ3": 800.0, "MQ7": 1000.0, "MQ135": 850.0}
REPLAY_ORDER = ("NoGas", "Smoke", "NoGas", "Perfume", "NoGas", "Mixture")
VC_MV, RL_KOHM, DIVIDER = 5000.0, 1.0, 1.5


def rs_from_pin(mv: float) -> float:
    vout = max(mv * DIVIDER, 1.0)
    return RL_KOHM * max(VC_MV - vout, 0.0) / vout


def pin_from_rs(rs: float) -> float:
    return VC_MV * RL_KOHM / (RL_KOHM + rs) / DIVIDER


def dataset_mv(row: dict, reference: dict) -> dict:
    """Satu baris dataset (ADC) -> mV pin ESP32 dengan Rs/R0 alat = nilai/median NoGas dataset."""
    return {s: round(pin_from_rs(float(row[s]) / reference[s] * rs_from_pin(CLEAN_PIN_MV[s])), 1) for s in SENSORS}


def replay_class(t: float, warmup: float, phase: float) -> str:
    if t < warmup:
        return "NoGas"
    return REPLAY_ORDER[int((t - warmup) // phase) % len(REPLAY_ORDER)]


def load_dataset(path: str) -> tuple[dict, dict]:
    rows: dict[str, list[dict]] = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["Gas"], []).append(r)
    nogas = rows["NoGas"]
    reference = {s: sorted(float(r[s]) for r in nogas)[len(nogas) // 2] for s in SENSORS}
    return rows, reference


def run_replay(a, token: str) -> int:
    path = a.csv
    try:
        rows, reference = load_dataset(path)
    except FileNotFoundError:
        print(f"{path} belum ada; jalankan dulu `make data-beta`.", file=sys.stderr)
        return 1
    rng, start, n = random.Random(a.seed), time.monotonic(), 0
    pos = {g: rng.randrange(len(v)) for g, v in rows.items()}
    # Baseline server = median 24 bacaan bersih pertama. NoGas bergeser di dalam sesinya (pemanasan), jadi mulai dari
    # tengah sesi agar baseline alat ≈ median NoGas dataset (penyebut rasio saat model dilatih).
    pos["NoGas"] = len(rows["NoGas"]) // 2 - 12
    print(f"Replay dataset {a.node} -> {a.url} (Simulated, format 4 MQ). Ctrl+C untuk berhenti.", flush=True)
    last = None
    while True:
        t = time.monotonic() - start
        gas = replay_class(t, a.warmup, a.phase)
        row = rows[gas][pos[gas] % len(rows[gas])]
        pos[gas] += 1
        payload = {"node_id": a.node, "uptime_s": int(t), "simulated": True,
                   **{f"{s.lower()}_mv": v for s, v in dataset_mv(row, reference).items()}}
        try:
            res = send(a.url, payload, token)
            if gas != last or n % 15 == 0:
                probs = res.get("probs") or {}
                top = f"{res.get('class')} {max(probs.values()):.2f}" if probs else "-"
                print(f"{int(t):5d}s  data {gas:8s} -> {res.get('state', '?'):10s} model {top}  {res.get('reason') or ''}",
                      flush=True)
        except urllib.error.HTTPError as e:
            print(f"{int(t):5d}s  HTTP {e.code}: {e.read()[:200].decode(errors='replace')}", file=sys.stderr, flush=True)
        except (urllib.error.URLError, OSError) as e:
            print(f"{int(t):5d}s  AirLens tidak terjangkau ({e}); mencoba lagi", file=sys.stderr, flush=True)
        last, n = gas, n + 1
        if a.count and n >= a.count:
            return 0
        time.sleep(max(0.0, a.interval - ((time.monotonic() - start) - t)))


def send(url: str, payload: dict, token: str, timeout: float = 4.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Node-Token": token} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", default="http://localhost:8080/api/sensor/readings")
    p.add_argument("--node", default="sim-01")
    p.add_argument("--interval", type=float, default=5.0, help="detik antar bacaan (ESP32: 5)")
    p.add_argument("--first-spike", type=float, default=360, help="detik sampai lonjakan asap pertama")
    p.add_argument("--spike-every", type=float, default=240)
    p.add_argument("--spike-length", type=float, default=45)
    p.add_argument("--count", type=int, default=0, help="jumlah bacaan lalu berhenti (0 = terus)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--replay", choices=["dataset"], help="putar ulang MultimodalGasData dalam format 4 MQ")
    p.add_argument("--csv", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw",
                                                 "multimodal_gas", "Gas_Sensors_Measurements.csv"))
    p.add_argument("--warmup", type=float, default=240, help="replay: detik udara bersih di awal (pemanasan + baseline)")
    p.add_argument("--phase", type=float, default=60, help="replay: detik per kelas")
    a = p.parse_args(argv)
    if a.replay:
        if a.interval == 5.0:
            a.interval = 2.0   # firmware 4 MQ mengirim tiap 2 detik
        if a.node == "sim-01":
            a.node = "sim-beta4-01"
        return run_replay(a, env_token("SENSOR_TOKEN"))
    rng, token, start, n = random.Random(a.seed), env_token("SENSOR_TOKEN"), time.monotonic(), 0
    print(f"Simulator {a.node} -> {a.url} (Simulated). Ctrl+C untuk berhenti.", flush=True)
    while True:
        t = time.monotonic() - start
        payload = {"node_id": a.node, "mq2_rs_kohm": rs_at(t, rng, first=a.first_spike, every=a.spike_every,
                                                            length=a.spike_length),
                   "uptime_s": int(t), "simulated": True}
        try:
            res = send(a.url, payload, token)
            ratio = res.get("ratio")
            print(f"{int(t):5d}s  Rs {payload['mq2_rs_kohm']:6.2f} kΩ  {res.get('state', '?'):10s}"
                  f"  ratio {ratio if ratio is not None else '-'}", flush=True)
        except urllib.error.HTTPError as e:
            print(f"{int(t):5d}s  HTTP {e.code}: {e.read()[:200].decode(errors='replace')}", file=sys.stderr, flush=True)
        except (urllib.error.URLError, OSError) as e:
            print(f"{int(t):5d}s  AirLens tidak terjangkau ({e}); mencoba lagi", file=sys.stderr, flush=True)
        n += 1
        if a.count and n >= a.count:
            return 0
        time.sleep(max(0.0, a.interval - ((time.monotonic() - start) - t)))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
