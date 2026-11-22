"""Kernel Kaggle AirLens (prompt 7): pipeline yang sama dengan `make lab-all PROFILE=lab`, tanpa Docker.

Dijalankan oleh Kaggle (akselerator GPU, internet aktif) setelah `make kaggle-push` di laptop. Input kernel:
- <user>/airlens-code          : kode repo (tarball dari laptop, commit tercatat di CODE_INFO.json)
- India-Nepal (adarshrouniyar/air-pollution-image-dataset-from-india-and-nepal): dipasang sebagai input.
- <user>/airlens-beta-recordings (opsional): CSV rekaman alat Beta dari lab (make beta-recordings-push).
PM25Vision (Hugging Face), Dhaka (Zenodo), dan MultimodalGasData (Mendeley) diunduh di dalam kernel.

Lingkungan: APP_PROFILE=kaggle, AIRLENS_DB=none (tanpa Postgres), MLflow SQLite di /tmp/airlens/mlflow.
Urutan: data foto -> model foto AQI tiga tingkat -> evaluasi -> data + model gas Beta (+ rekaman alat bila ada)
-> KEMAS -> referensi 5 kelas + compare_merge -> KEMAS.
Keluaran (/kaggle/working): airlens_results_kaggle_<waktu>.tar.gz (format sama dengan arsip lab, MANIFEST.sha256),
RINGKASAN.txt, timings.tsv. Saklar: SKIP_COMPARE=1 (edit ENV di bawah lalu push ulang).
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

# Saklar uji lokal (tidak dipakai di Kaggle): KERNEL_PROFILE=laptop, KERNEL_SKIP_GPU=1, KERNEL_SKIP_PIP=1,
# KERNEL_DATA_DIR, KERNEL_WORK, KERNEL_INPUT.
PROFILE = os.environ.get("KERNEL_PROFILE", "kaggle")
WORK = Path(os.environ.get("KERNEL_WORK", "/kaggle/working"))
TMP = Path(os.environ.get("KERNEL_TMP", "/tmp/airlens"))
INPUT = Path(os.environ.get("KERNEL_INPUT", "/kaggle/input"))
ENV_SWITCHES = {"SKIP_COMPARE": os.environ.get("SKIP_COMPARE", "0")}
# Versi sama dengan requirements/trainer.txt; torch/torchvision/numpy/pandas memakai bawaan image Kaggle (GPU).
PIP = ["mlflow-skinny==3.17.0", "alembic==1.20.0", "sqlalchemy==2.0.54", "onnx==1.23.2", "onnxruntime==1.31.0",
       "imagehash==4.3.2", "scikit-learn==1.9.1", "lightgbm==4.7.0", "shap==0.53.0", "pyyaml==6.0.3"]

LOG = WORK / "logs" / f"lab_{datetime.now():%Y%m%d_%H%M%S}_{PROFILE}"
TIMINGS = LOG / "timings.tsv"
SKIPPED: list[str] = []


def find_input(*names: str) -> Path | None:
    """Folder input Kaggle untuk salah satu nama slug (Kaggle memasang di /kaggle/input/<slug> atau /datasets/...)."""
    for name in names:
        for cand in list(INPUT.glob(name)) + list(INPUT.glob(f"**/{name}")):
            if cand.is_dir():
                return cand
    return None


def run(name: str, cmd: list[str], env: dict, critical: bool = True) -> bool:
    print(f"\n== {name}: mulai {datetime.now():%H:%M:%S}", flush=True)
    t0, start = time.time(), datetime.now().isoformat(timespec="seconds")
    with open(LOG / f"{name}.log", "w") as log:
        p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(TMP / "mlflow"))
        for line in p.stdout:
            sys.stdout.write(line)
            log.write(line)
        rc = p.wait()
    secs = int(time.time() - t0)
    status = "ok" if rc == 0 else f"gagal({rc})"
    with TIMINGS.open("a") as f:
        f.write(f"{name}\t{start}\t{datetime.now().isoformat(timespec='seconds')}\t{secs}\t{status}\n")
    print(f"== {name}: {status} dalam {secs // 60} mnt {secs % 60} dtk", flush=True)
    if rc != 0 and not critical:
        SKIPPED.append(f"{name} GAGAL (opsional, lihat logs/{LOG.name}/{name}.log)")
    return rc == 0


def skip(name: str, why: str) -> None:
    with TIMINGS.open("a") as f:
        f.write(f"{name}\t-\t-\t0\tdilewati({why})\n")
    SKIPPED.append(f"{name} ({why})")
    print(f"== {name}: DILEWATI ({why})", flush=True)


def summary(code: Path, main_failed: str | None) -> None:
    lines = [f"Ringkasan kaggle {datetime.now().isoformat(timespec='seconds')} · profil kaggle",
             TIMINGS.read_text(), ""]
    lines.append(f"STATUS: tahap utama '{main_failed}' GAGAL" if main_failed
                 else "STATUS: model foto AQI tiga tingkat + model gas Beta selesai dan terkemas")
    if SKIPPED:
        lines += ["Dilewati / gagal:"] + [f"  - {s}" for s in SKIPPED]
    results = code / "results"
    b = results / "beta_final.json"
    if b.exists():
        d = json.loads(b.read_text())
        t = d.get("test") or d.get("test_dataset") or {}
        lines.append(f"Model gas Beta v{d['version']} ({d['source']}): test macro-F1 {t.get('macro_f1', float('nan')):.3f}, "
                     f"recall asap {t.get('recall_smoke', float('nan')):.3f}")
    c = results / "compare_merge_3class.md"
    if c.exists():
        lines += ["compare_merge (5 kelas digabung vs 3 tingkat, test yang sama):", c.read_text()]
    text = "\n".join(lines) + "\n"
    (LOG / "RINGKASAN.txt").write_text(text)
    (WORK / "RINGKASAN.txt").write_text(text)


def export(code: Path, env: dict) -> None:
    out = subprocess.run([sys.executable, "-m", "airlens_trainer.export_archive", "--profile", PROFILE,
                          "--logs", str(WORK / "logs"), "--mlflow-dir", str(TMP / "mlflow"), "--out", str(WORK)],
                         env=env, cwd=str(code), capture_output=True, text=True)
    print(out.stdout[-2000:], out.stderr[-2000:], flush=True)
    if out.returncode != 0:
        SKIPPED.append("kemas GAGAL")


def main() -> int:
    LOG.mkdir(parents=True, exist_ok=True)
    TIMINGS.write_text("tahap\tmulai\tselesai\tdetik\tstatus\n")
    (TMP / "mlflow").mkdir(parents=True, exist_ok=True)

    # 1. Kode
    code_in = find_input("airlens-code")
    if code_in is None:
        print("GALAT: input 'airlens-code' tidak ada. Jalankan `make kaggle-push` dari laptop (mengunggah kode dulu).")
        return 2
    code = TMP / "AirLens"
    if not code.exists():
        tarball = next(code_in.rglob("airlens_code.tar.gz"), None)
        if tarball is not None:
            with tarfile.open(tarball) as t:
                t.extractall(TMP, filter="data")
        else:
            shutil.copytree(next(p.parent for p in code_in.rglob("Makefile")), code)
    info = json.loads((code / "CODE_INFO.json").read_text()) if (code / "CODE_INFO.json").exists() else {}
    print("kode:", info, flush=True)

    # 2. GPU
    import torch

    if os.environ.get("KERNEL_SKIP_GPU") != "1" and not torch.cuda.is_available():
        print("GALAT: GPU tidak tersedia. Aktifkan akselerator GPU di kernel (enable_gpu), pastikan akun Kaggle sudah "
              "diverifikasi nomor HP, dan kuota GPU mingguan belum habis.")
        return 3
    print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-", flush=True)

    # 3. Paket (unar: ekstrak arsip dataset Dhaka; ada di image Docker trainer, tidak ada di image Kaggle)
    if os.environ.get("KERNEL_SKIP_PIP") != "1":
        if shutil.which("unar") is None:
            subprocess.run("apt-get update -qq && apt-get install -y -qq unar", shell=True, check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *PIP], check=True)

    # 4. Lingkungan dan data input
    data = Path(os.environ.get("KERNEL_DATA_DIR", TMP / "data"))
    (data / "raw").mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **ENV_SWITCHES, "APP_PROFILE": PROFILE, "AIRLENS_DB": "none",
           "MLFLOW_TRACKING_URI": f"sqlite:///{TMP / 'mlflow' / 'mlflow.db'}",
           "AIRLENS_DATA_DIR": str(data), "AIRLENS_RESULTS_DIR": str(code / "results"),
           "AIRLENS_ARTIFACTS_DIR": str(code / "artifacts"), "AIRLENS_CONFIG_DIR": str(code / "config"),
           "PYTHONPATH": ":".join(str(code / d) for d in ("src", "api", "scheduler", "trainer")),
           "GIT_COMMIT": info.get("git_commit", ""), "TORCH_HOME": str(TMP / "torch")}
    india = find_input("air-pollution-image-dataset-from-india-and-nepal")
    if india:
        env["INDIA_NEPAL_DIR"] = str(india)
    recordings = find_input("airlens-beta-recordings")
    py = sys.executable

    # 5. Tahap utama (berantai)
    main_failed = None
    # Dua rantai terpisah: model foto dan model gas Beta tidak saling bergantung.
    beta_failed = None
    for chain in ([("data", [py, "-m", "airlens.data.pipeline"]), ("train", [py, "-m", "airlens_trainer.train"]),
                   ("eval", [py, "-m", "airlens_trainer.eval"])],
                  [("data-beta", [py, "-m", "airlens.data.beta_gas"]), ("train-beta", [py, "-m", "airlens_trainer.train_beta"])]):
        failed = None
        for name, cmd in chain:
            if failed:
                skip(name, f"tahap {failed} gagal")
            elif not run(name, cmd, env):
                failed = name
        if chain[0][0] == "data":
            main_failed = failed
        else:
            beta_failed = failed
    main_failed = main_failed or beta_failed
    if recordings and not beta_failed:
        csvs = ",".join(str(p) for p in sorted(recordings.rglob("*.csv")))
        run("beta-rekaman", [py, "-m", "airlens_trainer.import_beta_recordings"],
            {**env, "CSVS": csvs, "RETRAIN": "1", "PROMOTE_IF_BETTER": "1"}, critical=False)
    elif not recordings:
        skip("beta-rekaman", "belum ada dataset airlens-beta-recordings")

    summary(code, main_failed)
    export(code, env)                              # arsip pertama: dua model utama aman lebih dulu

    # 6. Tahap opsional
    if ENV_SWITCHES["SKIP_COMPARE"] == "1" or main_failed:
        why = "SKIP_COMPARE=1" if ENV_SWITCHES["SKIP_COMPARE"] == "1" else f"tahap utama {main_failed} gagal"
        skip("train-referensi-5kelas", why)
        skip("compare-merge", why)
    else:
        cand = next((code / "artifacts" / "models").glob("*/candidates.json"), None)   # model foto
        arch = json.loads(cand.read_text())["production"] if cand else "efficientnet_b0"
        ref_env = {**env, "TRAIN_CLASS_SCHEME": "epa5", "TRAIN_MODELS": arch}
        if run("train-referensi-5kelas", [py, "-m", "airlens_trainer.train"], ref_env, critical=False):
            run("compare-merge", [py, "-m", "airlens_trainer.lab_compare"], env, critical=False)
        else:
            skip("compare-merge", "referensi 5 kelas gagal")
        summary(code, main_failed)
        for old in WORK.glob(f"airlens_results_{PROFILE}_*.tar.gz"):
            old.unlink()                           # cukup arsip final (output Kaggle dibatasi 20 GB)
        export(code, env)
    summary(code, main_failed)
    print((WORK / "RINGKASAN.txt").read_text())
    return 0 if not main_failed else 1


if __name__ == "__main__":
    sys.exit(main())
