"""`make promote-beta`: challenger -> production untuk model gas Beta (`airlens-beta-gas`).

Kriteria di test dataset yang sama (data_version challenger = data sekarang): macro-F1 tidak turun dan recall asap
turun paling banyak `promote.max_smoke_recall_drop` (asap yang terlewat lebih berbahaya daripada alarm palsu).
Shadow mode Beta: API menghitung kelas challenger untuk setiap bacaan dan mencatatnya tanpa ditampilkan (bagian B);
ringkasannya ikut ditulis di laporan bila tersedia. Keputusan: results/promotion_beta_<waktu>.md.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from airlens.config import load_profile
from airlens.data.beta_gas import class_names, feature_names, load_beta_config
from airlens.data.manifest import read_data_version
from airlens.data.paths import RESULTS_DIR, processed_dir
from airlens.db.session import get_engine
from airlens.models import registry
from airlens.models.bundle import ARTIFACTS_DIR


def load_booster(bundle: Path):
    import lightgbm as lgb

    files = sorted(bundle.rglob("model.lgb")) + sorted(bundle.rglob("model.txt"))
    if not files:
        raise FileNotFoundError(f"model LightGBM tidak ditemukan di {bundle}")
    return lgb.Booster(model_file=str(files[0]))


def main() -> int:
    from airlens_trainer.train_beta import metrics

    profile, cfg = load_profile()["profile"], load_beta_config()
    model = cfg["registered_model"]
    prod_v, ch_v = registry.alias_version("production", model=model), registry.alias_version("challenger", model=model)
    if not ch_v or not prod_v:
        print(f"Butuh production dan challenger untuk {model} (production v{prod_v}, challenger v{ch_v}).")
        return 1
    data_dir = processed_dir(profile) / "beta_gas"
    table = pd.read_csv(data_dir / "features.csv")
    test = table[table["split"] == "test"]
    feats, classes = feature_names(cfg), class_names(cfg)
    y = np.array([classes.index(v) for v in test["label"]])
    res = {}
    for name, v in (("production", prod_v), ("challenger", ch_v)):
        bundle = registry.download_bundle(v, ARTIFACTS_DIR / "registry-cache", model=model)
        meta = json.loads((bundle / "metadata.json").read_text())
        pred = load_booster(bundle).predict(test[meta["features"]].to_numpy(dtype=float), raw_score=True).argmax(1)
        res[name] = {**metrics(y, pred, classes), "data_version": meta["data_version"]}
    p, c = res["production"], res["challenger"]
    drop = cfg["promote"]["max_smoke_recall_drop"]
    checks = [("Test sesuai data challenger", c["data_version"] == read_data_version(data_dir), c["data_version"][:12]),
              ("Macro-F1 challenger >= production", c["macro_f1"] >= p["macro_f1"], f"{c['macro_f1']:.3f} vs {p['macro_f1']:.3f}"),
              (f"Recall asap turun <= {drop}", c["recall_smoke"] >= p["recall_smoke"] - drop,
               f"{c['recall_smoke']:.3f} vs {p['recall_smoke']:.3f}")]
    ok = all(passed for _, passed, _ in checks)
    now = datetime.now(timezone.utc)
    lines = [f"# Promosi model gas Beta ({model}): {now:%Y-%m-%d %H:%M} UTC", "",
             f"Production v{prod_v} vs challenger v{ch_v}, test {len(y)} bacaan", "", "| Kriteria | Hasil | Detail |", "|---|---|---|"]
    lines += [f"| {n} | {'✅' if passed else '❌'} | {d} |" for n, passed, d in checks]
    lines += ["", f"Metrik: {json.dumps(res, ensure_ascii=False)}"]
    if ok:
        previous = registry.set_production(get_engine(), ch_v, model=model)
        registry.clear_challenger(model=model)
        lines += ["", f"**DIPROMOSIKAN**: v{previous} → v{ch_v}. Rollback: `make rollback-beta`."]
    else:
        lines += ["", "**DITOLAK**: production tidak berubah."]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"promotion_beta_{now:%Y%m%d_%H%M%S}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
