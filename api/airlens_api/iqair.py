"""Klien IQAir (AirVisual API v2, paket Community): pembanding real-time, BUKAN label latih.

- Cache per kota (default 15 menit) dari tabel iqair_readings: tidak memanggil API bila bacaan masih segar.
- Kuota dihitung dari tabel iqair_requests (semua panggilan, termasuk yang gagal): 5/menit, 500/hari.
- Lokasi browser: koordinat dibulatkan (0,05°) dan dipetakan ke kota terdekat lewat endpoint nearest_city,
  dengan cache di memori untuk TTL yang sama.
- Semua kegagalan (tanpa kunci, kuota habis, jaringan, kota tidak dikenal) menjadi IQAirUnavailable dengan alasan
  yang bisa ditampilkan; tidak pernah menggagalkan prediksi.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from airlens.db.models import IqairReading, IqairRequest

logger = logging.getLogger("airlens.api.iqair")
BASE_URL = "https://api.airvisual.com/v2"


class IQAirUnavailable(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Reading:
    id: int
    city: str
    state: str | None
    country: str | None
    aqi_us: int
    main_pollutant: str | None
    observed_at: datetime | None
    fetched_at: datetime
    cached: bool


class IQAirClient:
    def __init__(self, api_key: str, engine: Engine, ttl_seconds: int = 900, per_minute: int = 5,
                 per_day: int = 500, timeout: float = 8.0, base_url: str = BASE_URL):
        self.api_key, self.engine, self.ttl = api_key, engine, ttl_seconds
        self.per_minute, self.per_day, self.timeout, self.base_url = per_minute, per_day, timeout, base_url
        self._coord_cache: dict[tuple[float, float], tuple[float, tuple[str, str, str]]] = {}
        self._lock = threading.Lock()  # satu panggilan API pada satu waktu agar kuota tidak terlampaui

    # ------------------------------------------------------------------ cache & kuota
    def _fresh_reading(self, city: str, state: str, country: str) -> Reading | None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.ttl)
        with Session(self.engine) as s:
            row = s.scalars(select(IqairReading).where(
                IqairReading.city == city, IqairReading.state == state, IqairReading.country == country,
                IqairReading.fetched_at >= cutoff).order_by(IqairReading.fetched_at.desc()).limit(1)).first()
            return self._to_reading(row, cached=True) if row else None

    def _check_quota(self) -> None:
        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        with Session(self.engine) as s:
            last_min = s.scalar(select(func.count()).where(IqairRequest.requested_at >= now - timedelta(seconds=60)))
            today = s.scalar(select(func.count()).where(IqairRequest.requested_at >= day_start))
        if today >= self.per_day:
            raise IQAirUnavailable("kuota_harian", "Kuota harian IQAir habis; pembanding tersedia lagi besok.")
        if last_min >= self.per_minute:
            raise IQAirUnavailable("kuota_menit", "Batas panggilan IQAir per menit tercapai; coba lagi sebentar.")

    def _call(self, endpoint: str, params: dict) -> dict:
        if not self.api_key:
            raise IQAirUnavailable("tanpa_kunci", "Kunci IQAir belum diatur.")
        self._check_quota()
        status_code, ok = None, False
        try:
            r = requests.get(f"{self.base_url}/{endpoint}", params={**params, "key": self.api_key}, timeout=self.timeout)
            status_code = r.status_code
            body = r.json()
            ok = r.ok and body.get("status") == "success"
        except (requests.RequestException, ValueError) as exc:
            raise IQAirUnavailable("jaringan", f"IQAir tidak terjangkau ({type(exc).__name__}).") from None
        finally:
            with Session(self.engine) as s:
                s.add(IqairRequest(endpoint=endpoint, ok=ok, status_code=status_code))
                s.commit()
        if not ok:
            msg = str((body.get("data") or {}).get("message", "")) if isinstance(body, dict) else ""
            if status_code == 429 or "limit" in msg:
                raise IQAirUnavailable("kuota", "Batas panggilan IQAir tercapai.")
            if "not_found" in msg or "no_nearest" in msg:
                raise IQAirUnavailable("kota_tidak_dikenal", "Kota tidak ditemukan di IQAir.")
            raise IQAirUnavailable("galat", f"IQAir membalas galat ({msg or status_code}).")
        return body["data"]

    def _store(self, data: dict) -> Reading:
        pol = data["current"]["pollution"]
        coords = (data.get("location") or {}).get("coordinates") or [None, None]
        observed = datetime.fromisoformat(pol["ts"].replace("Z", "+00:00")) if pol.get("ts") else None
        with Session(self.engine) as s:
            row = IqairReading(city=data["city"], state=data.get("state"), country=data.get("country"),
                               lon=coords[0], lat=coords[1], aqi_us=int(pol["aqius"]),
                               main_pollutant=pol.get("mainus"), observed_at=observed, raw=data)
            s.add(row)
            s.commit()
            s.refresh(row)
            return self._to_reading(row, cached=False)

    @staticmethod
    def _to_reading(row: IqairReading, cached: bool) -> Reading:
        return Reading(id=row.id, city=row.city, state=row.state, country=row.country, aqi_us=row.aqi_us,
                       main_pollutant=row.main_pollutant, observed_at=row.observed_at, fetched_at=row.fetched_at,
                       cached=cached)

    # ------------------------------------------------------------------ API publik
    def by_city(self, city: str, state: str, country: str) -> Reading:
        with self._lock:
            fresh = self._fresh_reading(city, state, country)
            if fresh:
                return fresh
            return self._store(self._call("city", {"city": city, "state": state, "country": country}))

    def by_coords(self, lat: float, lon: float) -> Reading:
        key = (round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05)
        with self._lock:
            hit = self._coord_cache.get(key)
            if hit and time.monotonic() - hit[0] < self.ttl:
                fresh = self._fresh_reading(*hit[1])
                if fresh:
                    return fresh
            reading = self._store(self._call("nearest_city", {"lat": lat, "lon": lon}))
            self._coord_cache[key] = (time.monotonic(), (reading.city, reading.state, reading.country))
            return reading
