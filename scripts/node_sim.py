#!/usr/bin/env python3
"""Simulator node lengkap AirLens (Full version, concept): mengirim angka seperti Pi 5 + SEN66 + CO-B4 + kamera.

Hanya pustaka standar Python, jadi bisa dijalankan langsung di host:

    python3 scripts/node_sim.py cycle                    # semua kejadian bergiliran
    python3 scripts/node_sim.py smoke --url http://localhost:8080/api/node/readings

Skenario:
  normal         udara biasa (kamera bersih, CO ±2 ppm, indeks VOC ±100)
  smoke          kamera melihat asap + VOC dan PM2.5 naik            -> visible_smoke lalu smoke_confirmed
  invisible_gas  CO naik ke ±48 ppm, kamera bersih                    -> invisible_gas
  visible_smoke  kamera melihat asap, gas normal                      -> visible_smoke
  cycle          smoke, normal, invisible_gas, normal, visible_smoke, normal, ... (kejadian 60 s, jeda normal 90 s
                 agar setiap kejadian sempat ditutup back_to_normal)
Data selalu membawa "simulated": true; website memberi label "Simulated". Bila NODE_TOKEN ada di environment,
dikirim sebagai header X-Node-Token. Indeks VOC/NOx adalah indeks Sensirion, bukan ppm.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

SCENARIOS = ("normal", "smoke", "invisible_gas", "visible_smoke", "cycle")
CYCLE = (("smoke", 60), ("normal", 90), ("invisible_gas", 60), ("normal", 90), ("visible_smoke", 60), ("normal", 90))
GAS_LAG = 6.0   # pada skenario smoke, gas sampai ke sensor beberapa detik setelah asap terlihat kamera



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

def phase_at(scenario: str, t: float) -> tuple[str, float]:
    """(skenario aktif, detik sejak fase dimulai) pada detik t."""
    if scenario != "cycle":
        return scenario, t
    t %= sum(d for _, d in CYCLE)
    for name, dur in CYCLE:
        if t < dur:
            return name, t
        t -= dur
    return "normal", 0.0


def reading(scenario: str, t: float, rng: random.Random) -> dict:
    phase, tau = phase_at(scenario, t)
    n = lambda mu, sd: max(0.0, rng.gauss(mu, sd))  # noqa: E731
    smoke_seen = phase in ("smoke", "visible_smoke")
    gas_smoke = phase == "smoke" and tau >= GAS_LAG
    co = n(48, 3) if phase == "invisible_gas" else n(2, 0.5)
    return {
        "smoke_prob": round(min(1.0, n(0.92, 0.03)) if smoke_seen else min(1.0, n(0.05, 0.03)), 3),
        "co_ppm": round(co, 1),
        "pm25": round(n(65, 6) if gas_smoke else n(8, 1.5), 1),
        "pm10": round(n(90, 8) if gas_smoke else n(12, 2), 1),
        "co2_ppm": round(n(820, 20) if gas_smoke else n(610, 15)),
        "voc_index": round(min(500.0, max(1.0, n(320, 15) if gas_smoke else n(100, 8)))),
        "nox_index": round(min(500.0, max(1.0, n(20, 3) if gas_smoke else n(1, 0.3)))),
        "temp_c": round(n(28.0, 0.2), 1),
        "rh": round(min(100.0, n(61.0, 1.0)), 1),
    }


def send(url: str, payload: dict, token: str, timeout: float = 4.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Node-Token": token} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("scenario", choices=SCENARIOS, nargs="?", default="cycle")
    p.add_argument("--url", default="http://localhost:8080/api/node/readings")
    p.add_argument("--node", default="sim-full-01")
    p.add_argument("--interval", type=float, default=2.0, help="detik antar bacaan (node lengkap: 2)")
    p.add_argument("--count", type=int, default=0, help="jumlah bacaan lalu berhenti (0 = terus)")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)
    rng, token, start, n = random.Random(a.seed), env_token("NODE_TOKEN"), time.monotonic(), 0
    print(f"Simulator {a.node} ({a.scenario}) -> {a.url} (Simulated). Ctrl+C untuk berhenti.", flush=True)
    while True:
        t = time.monotonic() - start
        payload = {"node_id": a.node, "uptime_s": int(t), **reading(a.scenario, t, rng), "simulated": True}
        try:
            res = send(a.url, payload, token)
            phase = phase_at(a.scenario, t)[0]
            events = ", ".join(res.get("events", [])) or "-"
            print(f"{int(t):5d}s  {phase:13s} smoke {payload['smoke_prob']:.2f}  CO {payload['co_ppm']:5.1f} ppm  "
                  f"VOC idx {payload['voc_index']:3d}  kejadian: {events}", flush=True)
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
