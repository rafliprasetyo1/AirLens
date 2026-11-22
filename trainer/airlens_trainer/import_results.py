"""`make import-results ARCHIVE=<airlens_results_*.tar.gz>`: masukkan hasil lab (atau Kaggle) ke MLflow laptop.

Yang dilakukan (tidak ada data MLflow laptop yang ditimpa atau dihapus):
1. Ekstrak arsip ke data/import/<nama>/ (ekstraksi aman: tanpa path absolut/link keluar) dan periksa MANIFEST.sha256.
2. Cari bundle model foto AQI production (artifacts/models/<data_version>/candidates.json) dan bundle model gas Beta
   (results/beta_final.json, atau artifacts/models/beta_gas/.../lightgbm terbaru).
3. Tiap bundle didaftarkan lewat jalur yang sama dengan `make models-pull` (run baru + versi registry, ditandai
   sha256 paket) dan diberi alias ALIAS: bawaan **challenger**; ALIAS=production setelah metrik disetujui.
4. Bundle yang sha256-nya sudah pernah diimpor tidak didaftarkan ulang (aman diulang).
5. results/ dari arsip disalin ke results/imported/<nama>/ sebagai catatan.

Konfirmasi: bila alias tujuan sudah dipakai versi lain, alias itu akan berpindah ke versi impor. Tanpa CONFIRM=1 skrip bertanya
(atau berhenti bila tidak interaktif). Riwayat run lab lengkap tetap ada di arsip (mlflow_db.sql), tidak dipulihkan
ke laptop karena akan menimpa riwayat laptop.

Catatan: data_version lab berbeda dengan data laptop, sehingga `make promote` di laptop menolak challenger ini
(kriteria test yang sama). Untuk memakai model lab di laptop: `make rollback VERSION=<versi>` memasang production
langsung, ALIAS=production saat impor, atau `make models-pull`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

import mlflow
from mlflow import MlflowClient

from airlens.data.paths import DATA_DIR, RESULTS_DIR
from airlens.db.session import get_engine
from airlens.models import registry

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(archive: Path, dest_root: Path) -> Path:
    dest_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as t:
        names = {m.name.split("/")[0] for m in t.getmembers()}
        if len(names) != 1:
            raise ValueError(f"arsip harus berisi satu folder teratas, ditemukan {sorted(names)}")
        top = names.pop()
        if not (dest_root / top).exists():
            t.extractall(dest_root, filter="data")   # menolak path absolut, '..', dan link keluar
    return dest_root / top


def verify_manifest(root: Path) -> int:
    manifest = root / "MANIFEST.sha256"
    if not manifest.exists():
        raise ValueError("MANIFEST.sha256 tidak ada; arsip bukan hasil export_results.sh")
    bad, n = [], 0
    for line in manifest.read_text().splitlines():
        digest, rel = line.split(maxsplit=1)
        rel = rel.lstrip("*").removeprefix("./")
        p = root / rel
        n += 1
        if not p.exists() or sha256_file(p) != digest:
            bad.append(rel)
    if bad:
        raise ValueError(f"{len(bad)} berkas rusak/hilang, mis. {bad[:3]}; arsip ditolak")
    return n


def local_dir(root: Path, container_dir: str) -> Path:
    """Path bundle di candidates.json ditulis sebagai path container (/app/artifacts/...) -> path di arsip."""
    rel = container_dir.split("/artifacts/", 1)[-1]
    return root / "artifacts" / rel


def find_aqi_bundle(root: Path) -> Path | None:
    cands = sorted((root / "artifacts" / "models").glob("*/candidates.json"), key=lambda p: p.stat().st_mtime)
    for c in reversed(cands):
        d = json.loads(c.read_text())
        if d.get("production") and d["production"] in d.get("models", {}):
            b = local_dir(root, d["models"][d["production"]]["dir"])
            if (b / "metadata.json").exists():
                return b
    return None


BETA_MODEL = "airlens-beta-gas"


def find_beta_bundle(root: Path) -> Path | None:
    final = root / "results" / "beta_final.json"
    if final.exists():
        b = local_dir(root, json.loads(final.read_text())["bundle"])
        if (b / "metadata.json").exists():
            return b
    res = sorted((root / "artifacts" / "models" / "beta_gas").glob("*/lightgbm/metadata.json"), key=lambda p: p.stat().st_mtime)
    return res[-1].parent if res else None


def to_package_entry(bundle: Path, model: str, pkg: Path, archive_name: str) -> dict:
    """Salin bundle ke format paket models_dist (models/<nama>/...) dan buat entri manifest-nya."""
    from airlens_trainer.models_dist import key_metrics, sha256, source_of

    dest = pkg / "models" / model
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    shutil.copy2(bundle / "metadata.json", dest / "metadata.json")
    onnx_file = next(iter(sorted(bundle.rglob("*.onnx"))), None)
    if onnx_file:
        shutil.copy2(onnx_file, dest / "model.onnx")
        for extra in onnx_file.parent.glob("*.data"):
            shutil.copy2(extra, dest / extra.name)
    for name in ("model.lgb", "model.txt"):
        if (bundle / name).exists() and not onnx_file:
            shutil.copy2(bundle / name, dest / "model.lgb")
            break
    if (bundle / "plots").exists():
        shutil.copytree(bundle / "plots", dest / "plots")
    meta = json.loads((dest / "metadata.json").read_text())
    files = {str(p.relative_to(pkg)): {"sha256": sha256(p), "bytes": p.stat().st_size}
             for p in sorted(dest.rglob("*")) if p.is_file()}
    return {"name": model, "source_version": archive_name, "alias": os.environ.get("ALIAS", "challenger"),
            "kind": "onnx" if onnx_file else "lightgbm", "source": source_of(meta), "data_version": meta.get("data_version"),
            "metrics": key_metrics(model, meta), "files": files}


def confirm(models: list[str]) -> bool:
    alias = os.environ.get("ALIAS", "challenger")
    current = {m: registry.alias_version(alias, model=m) for m in models}
    taken = {m: v for m, v in current.items() if v}
    if not taken or os.environ.get("CONFIRM") == "1":
        return True
    text = ", ".join(f"{m} v{v}" for m, v in taken.items())
    if not sys.stdin.isatty():
        print(f"Alias {alias} sudah dipakai ({text}) dan akan dipindah. Jalankan ulang dengan CONFIRM=1.")
        return False
    return input(f"Alias {alias} sekarang: {text}. Pindahkan ke model impor? [y/N] ").strip().lower() in ("y", "ya", "yes")


def main() -> int:
    archive = Path(os.environ.get("ARCHIVE", ""))
    if not archive.is_file():
        print("Pakai: make import-results ARCHIVE=<path airlens_results_*.tar.gz>")
        return 1
    root = extract(archive, DATA_DIR / "import")
    n = verify_manifest(root)
    print(f"Arsip {archive.name}: {n} berkas, MANIFEST.sha256 cocok")
    targets = [(b, m) for b, m in ((find_aqi_bundle(root), registry.REGISTERED_MODEL), (find_beta_bundle(root), BETA_MODEL)) if b]
    if not targets:
        print("Tidak ada bundle model di arsip.")
        return 1
    if not confirm([m for _, m in targets]):
        print("Dibatalkan; tidak ada yang diubah.")
        return 1
    from airlens_trainer.models_dist import register

    client, engine = MlflowClient(), get_engine()
    pkg = root.parent / f"{root.name}.package"
    out = [register(to_package_entry(b, m, pkg, archive.name), pkg, client, engine) for b, m in targets]
    dest = RESULTS_DIR / "imported" / root.name
    if (root / "results").exists() and not dest.exists():
        shutil.copytree(root / "results", dest)
    for r in out:
        print(f"  {r['model']:18s} v{r['version']:>3} -> {r['alias']} ({r['status']}; metrik {r['metrics']})")
    print(f"Hasil arsip disalin ke {dest}. Setelah metrik disetujui: make import-results ARCHIVE=... ALIAS=production CONFIRM=1, "
          "lalu make models-publish MODELS_APPROVED=1.")
    summary = root / "logs"
    ring = sorted(summary.glob("lab_*/RINGKASAN.txt"))
    if ring:
        print("\n" + ring[-1].read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
