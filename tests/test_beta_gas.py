"""Model gas Beta: pemrosesan dataset, split per blok waktu (tanpa bocor), fitur, kelas, hash, model dimuat ulang,
dan additivity SHAP. Data uji = CSV sintetis dengan struktur MultimodalGasData (satu sesi berurutan per kelas)."""

import hashlib

import numpy as np
import pandas as pd
import pytest

from airlens.data import beta_gas

CFG = beta_gas.load_beta_config()
SESSION = 400


def _synthetic(n: int = SESSION, seed: int = 0) -> pd.DataFrame:
    """Empat sesi berurutan. Asap menurunkan MQ-2/MQ-135 (seperti dataset asli), alkohol menurunkan MQ-3 sedikit."""
    rng = np.random.default_rng(seed)
    level = {"NoGas": (750, 530, 610, 470), "Perfume": (740, 500, 630, 460),
             "Smoke": (600, 360, 575, 300), "Mixture": (585, 415, 450, 400)}
    rows = []
    for gas, (a, b, c, d) in level.items():
        drift = np.linspace(0, 20, n)
        for i in range(n):
            rows.append({"Serial Number": i, "MQ2": a + drift[i] + rng.normal(0, 6), "MQ3": b + rng.normal(0, 5),
                         "MQ5": 400, "MQ6": 400, "MQ7": c + rng.normal(0, 6), "MQ8": 500,
                         "MQ135": d + rng.normal(0, 5), "Gas": gas, "Corresponding Image Name": f"{i}_{gas}"})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ split
def test_block_split_purges_boundaries_and_covers_session():
    sp = CFG["split"]
    labels = beta_gas.block_split(1600, sp["blocks"], sp["pattern"], sp["purge_rows"])
    assert len(labels) == 1600
    kept = [(i, s) for i, s in enumerate(labels) if s]
    # tidak ada dua baris dari split berbeda yang berjarak <= 2*purge (bacaan berdekatan tidak terbelah)
    for (i, s), (j, t) in zip(kept, kept[1:]):
        if s != t:
            assert j - i > 2 * sp["purge_rows"], (i, j, s, t)
    # test dan val ada di tengah dan akhir sesi, bukan hanya di satu ujung
    idx = {s: [i for i, x in kept if x == s] for s in ("train", "val", "test")}
    assert min(idx["val"]) < 800 < max(idx["val"]) and max(idx["test"]) > 1400 and min(idx["test"]) < 1000
    assert set(labels) == {"train", "val", "test", ""}


def test_block_split_rejects_bad_pattern():
    with pytest.raises(ValueError):
        beta_gas.block_split(100, 3, ["train", "test"], 2)


# ------------------------------------------------------------------ pemrosesan
def test_build_features_classes_and_reference():
    table, info = beta_gas.build(_synthetic(), CFG)
    feats = beta_gas.feature_names(CFG)
    assert feats == ["r_mq2", "r_mq3", "r_mq7", "r_mq135", "mq3_over_mq2"]
    assert beta_gas.class_names(CFG) == ["clean_air", "alcohol", "smoke", "smoke_alcohol"]
    assert set(table["label"]) == set(beta_gas.class_names(CFG))
    assert table[feats].notna().all().all() and np.isfinite(table[feats].to_numpy()).all()
    # penyebut = median NoGas -> rasio udara bersih ±1, asap < 1 pada MQ-2 dan MQ-135
    med = table.groupby("label")[["r_mq2", "r_mq135"]].median()
    assert abs(med.loc["clean_air", "r_mq2"] - 1) < 0.02 and med.loc["smoke", "r_mq2"] < 0.85
    np.testing.assert_allclose(table["mq3_over_mq2"], table["r_mq3"] / table["r_mq2"])
    assert info["purged_rows"] > 0 and len(table) + info["purged_rows"] == 4 * SESSION
    assert set(table["split"]) == {"train", "val", "test"}


def test_build_rejects_unordered_session_and_unknown_class():
    df = _synthetic(50)
    bad = df.copy()
    bad.loc[(bad["Gas"] == "Smoke") & (bad["Serial Number"] == 10), "Serial Number"] = 99   # lompat
    with pytest.raises(ValueError, match="tidak berurutan"):
        beta_gas.build(bad, CFG)
    other = df.copy()
    other.loc[0, "Gas"] = "Ammonia"
    with pytest.raises(ValueError, match="tak dikenal"):
        beta_gas.build(other, CFG)


def test_fetch_rejects_corrupted_csv(tmp_path):
    data = _synthetic(10).to_csv(index=False).encode()
    cfg = {"data": {**CFG["data"], "sha256": hashlib.sha256(data).hexdigest()}}
    (tmp_path / CFG["data"]["filename"]).write_bytes(data)
    assert beta_gas.fetch_csv(cfg, tmp_path).exists()                     # hash cocok
    (tmp_path / CFG["data"]["filename"]).write_bytes(data[:-5] + b"00000")  # berkas rusak
    with pytest.raises(ValueError, match="sha256"):
        beta_gas.fetch_csv(cfg, tmp_path)


def test_device_features_follow_dataset_direction():
    """Di alat: gas -> Rs turun -> tegangan pin naik -> Rs/R0 < 1, searah dengan rasio dataset."""
    clean = {"MQ2": 900.0, "MQ3": 800.0, "MQ7": 1000.0, "MQ135": 850.0}
    base = {s: beta_gas.rs_from_mv(v) for s, v in clean.items()}
    f_clean = beta_gas.device_features(clean, base, CFG)
    assert all(abs(f_clean[f"r_{s.lower()}"] - 1) < 1e-9 for s in CFG["sensors"])
    smoky = {**clean, "MQ2": 1300.0, "MQ135": 1250.0}
    f = beta_gas.device_features(smoky, base, CFG)
    assert f["r_mq2"] < 0.8 and f["r_mq135"] < 0.8 and abs(f["r_mq3"] - 1) < 1e-9
    assert list(f) == beta_gas.feature_names(CFG)


# ------------------------------------------------------------------ model + SHAP
lgb = pytest.importorskip("lightgbm")


@pytest.fixture(scope="module")
def trained():
    from airlens_trainer.train_beta import train

    table, _ = beta_gas.build(_synthetic(), CFG)
    cfg = {**CFG, "model": {**CFG["model"], "n_estimators": 60}}
    booster, xs, ys, split = train(cfg, table)
    return booster, xs, ys, split


def test_model_reloads_with_identical_predictions(trained, tmp_path):
    booster, xs, _, _ = trained
    booster.save_model(str(tmp_path / "model.txt"))
    again = lgb.Booster(model_file=str(tmp_path / "model.txt"))
    np.testing.assert_allclose(again.predict(xs["test"], raw_score=True), booster.predict(xs["test"], raw_score=True))
    assert booster.predict(xs["test"]).shape == (len(xs["test"]), 4)


def test_shap_additivity_and_matches_shap_library(trained):
    from airlens_trainer.train_beta import shap_contrib

    booster, xs, _, _ = trained
    contrib = shap_contrib(booster, xs["test"], 4)                       # (n, kelas, fitur + 1)
    assert contrib.shape == (len(xs["test"]), 4, 6)
    raw = booster.predict(xs["test"], raw_score=True)
    np.testing.assert_allclose(contrib.sum(-1), raw, atol=1e-9)           # nilai dasar + SHAP = skor kelas
    shap = pytest.importorskip("shap")
    sv = np.asarray(shap.TreeExplainer(booster).shap_values(xs["test"][:20]))
    if sv.shape[1] != 5:
        sv = np.moveaxis(sv, 0, -1)
    np.testing.assert_allclose(np.moveaxis(sv, -1, 1), contrib[:20, :, :-1], atol=1e-6)


def test_metrics_baseline_and_names(trained):
    from airlens_trainer.train_beta import baseline_rule, metrics, pretty_name

    booster, xs, ys, split = trained
    classes = beta_gas.class_names(CFG)
    m = metrics(ys["test"], booster.predict(xs["test"]).argmax(1), classes)
    assert set(m["f1"]) == set(classes) and m["macro_f1"] > 0.8      # data sintetis mudah dipisah
    base = baseline_rule(split["test"], classes, 0.6)
    assert set(np.unique(base)) <= {classes.index("smoke"), classes.index("clean_air")}
    assert pretty_name("r_mq135") == "MQ-135" and pretty_name("mq3_over_mq2") == "MQ-3 / MQ-2"


def test_api_side_functions_do_not_need_pandas():
    """Image API tidak memasang pandas: modul ini harus bisa diimpor dan dipakai untuk fitur alat tanpa pandas."""
    import subprocess
    import sys

    code = ("import sys; sys.modules['pandas'] = None\n"
            "from airlens.data import beta_gas as b\n"
            "cfg = b.load_beta_config()\n"
            "mv = {'MQ2': 900.0, 'MQ3': 800.0, 'MQ7': 1000.0, 'MQ135': 850.0}\n"
            "base = {k: b.rs_from_mv(v) for k, v in mv.items()}\n"
            "assert abs(b.device_features(mv, base, cfg)['r_mq2'] - 1) < 1e-9\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
