"""Konversi PM2.5 <-> AQI US EPA.

Sumber tabel (diverifikasi 2026-10-24):
- 2024: EPA, "Technical Assistance Document for the Reporting of Daily Air Quality - the AQI",
  EPA-454/B-24-002 (Mei 2024), Table 6, berlaku sejak 6 Mei 2024. Hazardous 225.5+ (AQI 301+),
  AQI 500 = 325.4 ug/m3; di atasnya diekstrapolasi dengan persamaan yang sama.
- 2012: kolom "Previous AQI Category Breakpoints" di EPA "Final Updates to the AQI for Particulate
  Matter - Fact Sheet" (Feb 2024). Hanya dipakai untuk membalik nilai AQI lama ke konsentrasi.
Aturan: konsentrasi dipotong (truncate) ke 1 desimal, indeks dibulatkan ke bilangan bulat terdekat.
"""

import math
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

AQI_TABLE_VERSION = "EPA-454/B-24-002 (2024)"

CATEGORIES = ("good", "moderate", "usg", "unhealthy", "very_unhealthy", "hazardous")
CATEGORY_LABELS = {
    "good": "Baik",
    "moderate": "Sedang",
    "usg": "Tidak sehat bagi kelompok sensitif",
    "unhealthy": "Tidak sehat",
    "very_unhealthy": "Sangat tidak sehat",
    "hazardous": "Berbahaya",
}

# (konsentrasi rendah, konsentrasi tinggi, indeks rendah, indeks tinggi, kategori)
BREAKPOINTS = {
    2024: (
        (0.0, 9.0, 0, 50, "good"),
        (9.1, 35.4, 51, 100, "moderate"),
        (35.5, 55.4, 101, 150, "usg"),
        (55.5, 125.4, 151, 200, "unhealthy"),
        (125.5, 225.4, 201, 300, "very_unhealthy"),
        (225.5, 325.4, 301, 500, "hazardous"),
    ),
    2012: (
        (0.0, 12.0, 0, 50, "good"),
        (12.1, 35.4, 51, 100, "moderate"),
        (35.5, 55.4, 101, 150, "usg"),
        (55.5, 150.4, 151, 200, "unhealthy"),
        (150.5, 250.4, 201, 300, "very_unhealthy"),
        (250.5, 350.4, 301, 400, "hazardous"),
        (350.5, 500.4, 401, 500, "hazardous"),
    ),
}


def truncate_pm25(conc: float) -> float:
    if conc is None or math.isnan(conc) or conc < 0:
        raise ValueError(f"konsentrasi PM2.5 tidak valid: {conc!r}")
    # Decimal dari repr menghindari galat biner (mis. 35.5 tersimpan sebagai 35.4999...).
    return float(Decimal(repr(conc)).quantize(Decimal("0.1"), rounding=ROUND_FLOOR))


def _segment(c: float, table: int) -> tuple:
    rows = BREAKPOINTS[table]
    for row in rows:
        if c <= row[1]:
            return row
    return rows[-1]  # di atas batas tabel: ekstrapolasi segmen terakhir


def pm25_to_category(conc: float, table: int = 2024) -> str:
    return _segment(truncate_pm25(conc), table)[4]


def pm25_to_aqi(conc: float, table: int = 2024) -> int:
    c = truncate_pm25(conc)
    bp_lo, bp_hi, i_lo, i_hi, _ = _segment(c, table)
    index = (i_hi - i_lo) / (bp_hi - bp_lo) * (c - bp_lo) + i_lo
    return int(Decimal(repr(index)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def aqi_to_pm25(aqi: float, table: int = 2012) -> float:
    """Balik indeks AQI ke konsentrasi (perkiraan; indeks asli sudah dibulatkan, galat <= setengah langkah)."""
    if aqi is None or math.isnan(aqi) or aqi < 0:
        raise ValueError(f"nilai AQI tidak valid: {aqi!r}")
    rows = BREAKPOINTS[table]
    row = next((r for r in rows if aqi <= r[3]), rows[-1])
    bp_lo, bp_hi, i_lo, i_hi, _ = row
    return (aqi - i_lo) * (bp_hi - bp_lo) / (i_hi - i_lo) + bp_lo


def aqi_to_category(aqi: float) -> str:
    """Kategori dari indeks; batas indeks (50/100/150/200/300) sama di tabel 2012 dan 2024."""
    for limit, cat in ((50, "good"), (100, "moderate"), (150, "usg"), (200, "unhealthy"), (300, "very_unhealthy")):
        if aqi <= limit:
            return cat
    return "hazardous"
