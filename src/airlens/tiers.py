"""Skema tiga tingkat AirLens (satu sumber kebenaran untuk trainer, API, monitoring, dan halaman web).

| id        | Inggris  | Indonesia  | Kategori AQI US EPA asal                       | Rentang AQI |
|-----------|----------|------------|------------------------------------------------|-------------|
| low       | Low      | Rendah     | Good + Moderate                                | 0–100       |
| elevated  | Elevated | Meningkat  | Unhealthy for sensitive groups + Unhealthy     | 101–200     |
| high      | High     | Tinggi     | Very unhealthy + Hazardous                     | 201+        |

Kenapa bukan "Moderate/Sedang": IQAir memakai kata itu untuk AQI 51–100, yang di AirLens masuk "Low"; kata yang sama
akan membingungkan saat dibandingkan dengan baseline IQAir (docs/prompts/5_laptop_sebelum_lab.md bagian I).

Kompatibilitas: model lama 3 kelas memakai nama gabungan EPA (moderate/unhealthy/very_unhealthy) dengan
penggabungan yang sama; nama itu dipetakan ke tingkat baru saat ditampilkan (LEGACY_NAMES), sehingga rollback aman.
Model 5 kelas tetap ditampilkan sebagai kategori EPA aslinya.
"""

from __future__ import annotations

from airlens.aqi import CATEGORIES, aqi_to_category

SCHEME = "airlens-3tier-v1"
TIER_IDS = ("low", "elevated", "high")

# Kategori EPA -> tingkat (dipakai sebagai data.class_merge di config/laptop.yaml dan config/lab.yaml)
TIER_MERGE = {"good": "low", "moderate": "low", "usg": "elevated", "unhealthy": "elevated",
              "very_unhealthy": "high", "hazardous": "high"}

TIERS = {
    "low": {
        "label_en": "Low", "label_id": "Rendah", "aqi_range": (0, 100), "color": "#00E400", "text_color": "#0b0b0b",
        "epa": ("good", "moderate"),
        "advice_id": "Aktivitas di luar ruangan seperti biasa. Orang yang sangat sensitif dapat mengurangi aktivitas "
                     "berat yang lama di luar.",
        "advice_en": "Outdoor activity as usual. Very sensitive people may reduce long, intense activity outdoors.",
    },
    "elevated": {
        "label_en": "Elevated", "label_id": "Meningkat", "aqi_range": (101, 200), "color": "#FF7E00",
        "text_color": "#0b0b0b", "epa": ("usg", "unhealthy"),
        "advice_id": "Kelompok sensitif (anak, lansia, penderita asma atau penyakit jantung) membatasi aktivitas berat "
                     "di luar ruangan; yang lain mengurangi aktivitas berat yang lama.",
        "advice_en": "Sensitive groups (children, older adults, people with asthma or heart disease) limit intense "
                     "outdoor activity; everyone else cuts down on long, intense activity.",
    },
    "high": {
        "label_en": "High", "label_id": "Tinggi", "aqi_range": (201, 500), "color": "#8F3F97", "text_color": "#ffffff",
        "epa": ("very_unhealthy", "hazardous"),
        "advice_id": "Semua orang menghindari aktivitas berat di luar ruangan; kelompok sensitif tetap di dalam "
                     "ruangan. Bila harus keluar, gunakan masker yang sesuai (mis. N95).",
        "advice_en": "Everyone avoids intense outdoor activity; sensitive groups stay indoors. If you must go out, "
                     "wear a suitable mask (e.g. N95).",
    },
}

# Nama kelas model 3 kelas lama -> tingkat baru (penggabungan sama: good->moderate, usg->unhealthy, hazardous->very_unhealthy)
LEGACY_NAMES = {"moderate": "low", "unhealthy": "elevated", "very_unhealthy": "high"}
LEGACY_MERGE = {"good": "moderate", "usg": "unhealthy", "hazardous": "very_unhealthy"}


def is_legacy_three_class(classes: list[str], merge: dict[str, str] | None) -> bool:
    """Model 3 kelas dengan nama lama dan penggabungan yang setara dengan skema tiga tingkat."""
    if list(classes) != ["moderate", "unhealthy", "very_unhealthy"]:
        return False
    return not merge or all(merge.get(k, k) == v for k, v in LEGACY_MERGE.items())


def normalize_classes(classes: list[str], merge: dict[str, str] | None = None) -> list[str]:
    """Daftar kelas dengan nama tingkat baru bila model memakai skema tiga tingkat lama; selain itu apa adanya.
    Dipakai promote untuk memutuskan apakah dua model memakai skema yang sama."""
    return [LEGACY_NAMES[c] for c in classes] if is_legacy_three_class(classes, merge) else list(classes)


def tier_of(cls: str, classes: list[str], merge: dict[str, str] | None = None) -> str | None:
    """Tingkat untuk kelas model, atau None bila model bukan skema tiga tingkat (mis. 5 kelas)."""
    if cls in TIERS:
        return cls
    if is_legacy_three_class(classes, merge):
        return LEGACY_NAMES.get(cls)
    return None


def aqi_to_tier(aqi: float) -> str:
    """Tingkat dari indeks AQI US (IQAir): 0–100 low, 101–200 elevated, 201+ high."""
    return TIER_MERGE[aqi_to_category(aqi)]


def tier_view(tier: str, lang: str = "id") -> dict:
    t = TIERS[tier]
    return {"key": tier, "label": t[f"label_{lang}"], "label_en": t["label_en"], "label_id": t["label_id"],
            "aqi_range": list(t["aqi_range"]), "color": t["color"], "text_color": t["text_color"],
            "advice": t[f"advice_{lang}"], "advice_en": t["advice_en"], "scheme": SCHEME}


assert set(TIER_MERGE) == set(CATEGORIES) and set(TIER_MERGE.values()) == set(TIER_IDS)
