"""`make kaggle-push | kaggle-status | kaggle-pull`: menjalankan pelatihan di Kaggle Notebook dari laptop (Kaggle CLI).

push       : unggah kode (build/kaggle/code: tarball + CODE_INFO.json, dari working tree) sebagai versi baru dataset
             privat <user>/airlens-code, lalu push kernel <user>/airlens-train (GPU + internet) dengan input kode,
             India-Nepal, dan (bila ada) rekaman alat Beta. Kernel langsung berjalan di Kaggle.
recordings : unggah CSV rekaman alat (build/kaggle/recordings) sebagai dataset privat <user>/airlens-beta-recordings.
status : status kernel (queued/running/complete/error).
pull   : unduh keluaran kernel, periksa arsip (MANIFEST.sha256), salin ke results/, tampilkan RINGKASAN + metrik.
Kredensial: KAGGLE_USERNAME / KAGGLE_KEY dari .env (diteruskan compose ke container trainer), tidak pernah dicetak.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from airlens.data.paths import RESULTS_DIR

BUILD = Path(os.environ.get("KAGGLE_BUILD_DIR", "/kaggle_build"))
REPO_KERNEL = Path(__file__).resolve().parents[2] / "kaggle" / "kernel"
INPUT_DATASETS = ["adarshrouniyar/air-pollution-image-dataset-from-india-and-nepal"]
HINTS = [
    (("phone", "verif"), "Akun Kaggle belum diverifikasi nomor HP. Verifikasi di kaggle.com → Settings → Phone "
                         "verification (wajib untuk GPU dan internet di kernel)."),
    (("quota", "gpu limit", "exceeded"), "Kuota GPU Kaggle minggu ini habis. Tunggu reset mingguan, atau pakai jalur lab "
                                         "(make lab-all PROFILE=lab)."),
    (("401", "unauthorized"), "Kredensial Kaggle salah. Periksa KAGGLE_USERNAME dan KAGGLE_KEY di .env (buat token baru "
                              "di kaggle.com → Settings → API)."),
    (("403", "forbidden", "permission"), "Akses ditolak Kaggle: periksa kredensial, verifikasi HP, dan persetujuan aturan "
                                        "dataset input (buka halaman datasetnya sekali di browser)."),
    (("404", "not found", "does not exist"), "Dataset/kernel tidak ditemukan di Kaggle. Untuk push pertama ini normal "
                                            "(dibuat otomatis); bila tetap gagal periksa nama pengguna."),
]


def user() -> str:
    u = os.environ.get("KAGGLE_USERNAME", "")
    if not u or not os.environ.get("KAGGLE_KEY"):
        raise SystemExit("KAGGLE_USERNAME / KAGGLE_KEY kosong di .env. Isi dari kaggle.com → Settings → API → Create New Token.")
    return u


def explain(text: str) -> str:
    low = text.lower()
    for keys, hint in HINTS:
        if any(k in low for k in keys):
            return hint
    return "Lihat pesan Kaggle di atas."


def kaggle(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["kaggle", *args], capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    if check and p.returncode != 0:
        print(out.strip()[-1500:])
        raise SystemExit(f"GALAT kaggle {args[0]} {args[1] if len(args) > 1 else ''}: {explain(out)}")
    return p


def push_code(u: str) -> str:
    code = BUILD / "code"
    if not (code / "airlens_code.tar.gz").exists():
        raise SystemExit("build/kaggle/code/airlens_code.tar.gz belum ada (dibuat oleh `make kaggle-push`).")
    info = json.loads((code / "CODE_INFO.json").read_text())
    (code / "dataset-metadata.json").write_text(json.dumps(
        {"title": "airlens-code", "id": f"{u}/airlens-code", "licenses": [{"name": "other"}]}, indent=2))
    exists = kaggle("datasets", "status", f"{u}/airlens-code", check=False).returncode == 0
    if exists:
        kaggle("datasets", "version", "-p", str(code), "-m", f"kode {info.get('git_commit')}", "-q")
    else:
        kaggle("datasets", "create", "-p", str(code), "-q")   # privat secara bawaan
    print(f"kode {info.get('git_commit')} diunggah ke {u}/airlens-code (privat)")
    return info.get("git_commit", "")


def wait_dataset_ready(u: str, timeout: int = 600) -> None:
    import time

    t0 = time.time()
    while time.time() - t0 < timeout:
        p = kaggle("datasets", "status", f"{u}/airlens-code", check=False)
        if "ready" in (p.stdout + p.stderr).lower():
            return
        time.sleep(10)
    print("peringatan: dataset kode belum 'ready' setelah 10 menit; kernel tetap di-push")


def push(u: str) -> int:
    commit = push_code(u)
    wait_dataset_ready(u)
    kdir = BUILD / "kernel"
    kdir.mkdir(parents=True, exist_ok=True)
    extra = [f"{u}/airlens-beta-recordings"] if kaggle("datasets", "status", f"{u}/airlens-beta-recordings",
                                                       check=False).returncode == 0 else []
    if extra:
        print("rekaman alat Beta ikut dipakai (model Beta dilatih ulang dengan dataset publik + rekaman)")
    if not (kdir / "run.py").exists():   # disalin scripts/kaggle.sh dari kaggle/kernel/run.py
        shutil.copy2(REPO_KERNEL / "run.py", kdir / "run.py")
    (kdir / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{u}/airlens-train", "title": "airlens-train", "code_file": "run.py", "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [f"{u}/airlens-code", *INPUT_DATASETS, *extra], "competition_sources": [], "kernel_sources": []},
        indent=2))
    p = kaggle("kernels", "push", "-p", str(kdir))
    print(p.stdout.strip())
    print(f"Kernel {u}/airlens-train berjalan di Kaggle (kode {commit}). Pantau: make kaggle-status, "
          f"atau https://www.kaggle.com/code/{u}/airlens-train. Perkiraan 2–4 jam.")
    return 0


def status(u: str) -> int:
    p = kaggle("kernels", "status", f"{u}/airlens-train")
    print(p.stdout.strip())
    return 0


def pull(u: str) -> int:
    from airlens_trainer.import_results import verify_manifest

    out = BUILD / "output"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    st = kaggle("kernels", "status", f"{u}/airlens-train").stdout.lower()
    if "complete" not in st:
        print(st.strip())
        if "error" in st:
            print("Kernel gagal. Log lengkap: make kaggle-pull tetap mengunduh log, atau buka halaman kernel.")
        else:
            print("Kernel belum selesai. Coba lagi nanti (make kaggle-status).")
    kaggle("kernels", "output", f"{u}/airlens-train", "-p", str(out), "-q")
    archives = sorted(out.rglob("airlens_results_kaggle_*.tar.gz"))
    ring = next(out.rglob("RINGKASAN.txt"), None)
    if ring:
        print(ring.read_text())
    if not archives:
        print("Tidak ada arsip hasil di keluaran kernel (lihat log di build/kaggle/output/).")
        return 1
    archive = archives[-1]
    check = BUILD / "check"
    shutil.rmtree(check, ignore_errors=True)
    check.mkdir()
    with tarfile.open(archive) as t:
        t.extractall(check, filter="data")
    root = next(p for p in check.iterdir() if p.is_dir())
    n = verify_manifest(root)
    must = ["artifacts/models", "results", "logs", "ENVIRONMENT.txt"]
    missing = [m for m in must if not (root / m).exists()]
    beta = root / "results" / "beta_final.json"
    cands = sorted((root / "artifacts" / "models").glob("*/candidates.json"))
    print(f"Arsip {archive.name}: {n} berkas, MANIFEST cocok; bagian wajib {'lengkap' if not missing else 'KURANG: ' + ', '.join(missing)}")
    if cands:
        c = json.loads(cands[-1].read_text())
        best = c["models"][c["production"]]
        print(f"Model AQI tiga tingkat: {c['production']} (val macro-F1 {best['val_macro_f1']:.3f})")
    if beta.exists():
        d = json.loads(beta.read_text())
        t = d.get("test") or d.get("test_dataset") or {}
        print(f"Model gas Beta ({d['source']}): test macro-F1 {t.get('macro_f1', 0):.3f}, recall asap {t.get('recall_smoke', 0):.3f}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESULTS_DIR / archive.name
    shutil.copy2(archive, dest)
    shutil.rmtree(check, ignore_errors=True)
    print(f"Disalin ke results/{archive.name}. Impor ke MLflow laptop: make import-results ARCHIVE=results/{archive.name}")
    return 0 if not missing else 1


def recordings(u: str) -> int:
    folder = BUILD / "recordings"
    csvs = sorted(folder.glob("*.csv"))
    if not csvs:
        raise SystemExit("Tidak ada CSV di build/kaggle/recordings (pakai: make beta-recordings-push CSV=<berkas>).")
    (folder / "dataset-metadata.json").write_text(json.dumps(
        {"title": "airlens-beta-recordings", "id": f"{u}/airlens-beta-recordings", "licenses": [{"name": "other"}]}, indent=2))
    if kaggle("datasets", "status", f"{u}/airlens-beta-recordings", check=False).returncode == 0:
        kaggle("datasets", "version", "-p", str(folder), "-m", f"{len(csvs)} rekaman", "-q")
    else:
        kaggle("datasets", "create", "-p", str(folder), "-q")
    print(f"{len(csvs)} CSV rekaman diunggah ke {u}/airlens-beta-recordings (privat). Lanjutkan: make kaggle-push")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    u = user()
    return {"push": push, "status": status, "pull": pull, "recordings": recordings}.get(
        cmd, lambda _: print("push|status|pull|recordings") or 1)(u)


if __name__ == "__main__":
    sys.exit(main())
