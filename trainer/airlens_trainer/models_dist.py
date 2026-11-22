"""Paket model final dan distribusinya ke dua mesin (prompt 7 bagian B) lewat dataset Kaggle privat `airlens-models`.

    python -m airlens_trainer.models_dist publish   (make models-publish)
    python -m airlens_trainer.models_dist pull      (make models-pull [VERSION=n])

publish: versi production `airlens-aqi` (foto) dan `airlens-beta-gas` (sensor Beta) dari MLflow mesin ini dikemas ke
  build/models/package/models/<nama>/ (ONNX atau LightGBM, metadata.json, plot) + manifest.json
  (nama, versi, alias tujuan, metrik utama, sumber pelatihan kaggle/lab/laptop, commit, tanggal, sha256 tiap berkas).
  Metrik ditampilkan; unggah ke Kaggle HANYA bila MODELS_APPROVED=1 (persetujuan pemilik). PUBLISH_ONLY_BUILD=1 = kemas saja.
pull: unduh versi tertentu (bawaan terbaru), periksa sha256 (berkas rusak = ditolak, tidak ada yang diimpor), daftarkan
  ke MLflow mesin ini dan pasang alias sesuai manifest. Model yang sha256-nya sudah terdaftar dipakai ulang (tidak dobel),
  sehingga perintah ini aman diulang. PULL_DIR=<folder paket> = lewati unduhan (uji / salinan manual).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MODELS = ("airlens-aqi", "airlens-beta-gas")
DATASET_SLUG = "airlens-models"
BUILD = Path(os.environ.get("MODELS_BUILD_DIR", "/models_build"))
FORMAT = 1


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_of(meta: dict) -> str:
    prof = meta.get("profile") or ""
    return prof if prof in ("kaggle", "lab", "laptop") else "laptop"


def key_metrics(model: str, meta: dict) -> dict:
    test = meta.get("test_metrics") or {}
    val = meta.get("val_metrics") or meta.get("val") or {}
    if model == "airlens-beta-gas":
        keys, src = ("macro_f1", "recall_smoke", "accuracy"), test
    else:
        keys, src = ("macro_f1", "balanced_accuracy", "ece"), (test or val)
    return {k: round(float(src[k]), 4) for k in keys if isinstance(src.get(k), (int, float))}


# ------------------------------------------------------------------ kemas
def collect(model: str, version: str, dest: Path) -> dict:
    """Unduh bundle versi registry ke dest (berkas datar) dan kembalikan entri manifest."""
    import mlflow
    from mlflow import MlflowClient

    from airlens.models import registry

    tmp = dest.parent / f".{dest.name}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    bundle = registry.download_bundle(version, tmp, model=model)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(bundle / "metadata.json", dest / "metadata.json")
    onnx_file = next(iter(sorted(bundle.rglob("*.onnx"))), None)
    if onnx_file:
        shutil.copy2(onnx_file, dest / "model.onnx")
        for extra in onnx_file.parent.glob("*.data"):   # bobot ONNX eksternal: nama harus tetap (dirujuk dari model)
            shutil.copy2(extra, dest / extra.name)
    lgb_file = next(iter(sorted(bundle.rglob("model.lgb"))), None)
    if lgb_file:
        shutil.copy2(lgb_file, dest / "model.lgb")
    run_id = MlflowClient().get_model_version(model, version).run_id
    try:
        got = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="plots", dst_path=str(tmp / "plots"))
        shutil.copytree(got, dest / "plots", dirs_exist_ok=True)
    except Exception:
        pass
    shutil.rmtree(tmp, ignore_errors=True)
    meta = json.loads((dest / "metadata.json").read_text())
    files = {str(p.relative_to(dest.parent.parent)): {"sha256": sha256(p), "bytes": p.stat().st_size}
             for p in sorted(dest.rglob("*")) if p.is_file()}
    return {"name": model, "source_version": str(version), "alias": "production", "kind": "lightgbm" if (dest / "model.lgb").exists() else "onnx",
            "source": source_of(meta), "data_version": meta.get("data_version"), "metrics": key_metrics(model, meta),
            "git_commit": meta.get("git_commit"), "dev_model": bool(meta.get("dev_model") or meta.get("smoke")),
            "files": files}


def build_package(out: Path, versions: dict[str, str]) -> dict:
    shutil.rmtree(out, ignore_errors=True)
    (out / "models").mkdir(parents=True)
    entries = [collect(m, v, out / "models" / m) for m, v in versions.items()]
    manifest = {"format": FORMAT, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "git_commit": os.environ.get("GIT_COMMIT", ""), "models": entries}
    manifest["package_sha256"] = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


# ------------------------------------------------------------------ periksa + impor
class PackageError(Exception):
    pass


def verify_package(root: Path) -> dict:
    """manifest ada dan setiap berkas cocok sha256-nya; satu saja rusak/hilang -> PackageError (tidak ada yang diimpor)."""
    mf = root / "manifest.json"
    if not mf.exists():
        raise PackageError("manifest.json tidak ada di paket")
    manifest = json.loads(mf.read_text())
    if manifest.get("format") != FORMAT:
        raise PackageError(f"format paket {manifest.get('format')} tidak dikenal")
    bad = []
    for e in manifest["models"]:
        for rel, info in e["files"].items():
            p = root / rel
            if not p.exists() or sha256(p) != info["sha256"]:
                bad.append(rel)
    if bad:
        raise PackageError(f"{len(bad)} berkas rusak atau hilang (mis. {bad[:3]}); paket ditolak, tidak ada yang diimpor")
    return manifest


def entry_sha(entry: dict) -> str:
    return hashlib.sha256(json.dumps(entry["files"], sort_keys=True).encode()).hexdigest()


def existing_version(client, model: str, sha: str) -> str | None:
    try:
        for v in client.search_model_versions(f"name='{model}'"):
            if (v.tags or {}).get("package_sha") == sha:
                return v.version
    except Exception:
        return None
    return None


def register(entry: dict, root: Path, client, engine) -> dict:
    import mlflow

    from airlens.models import registry

    model, sha = entry["name"], entry_sha(entry)
    folder = root / "models" / model
    meta = json.loads((folder / "metadata.json").read_text())
    version = existing_version(client, model, sha)
    status = "sudah ada"
    if version is None:
        mlflow.set_experiment("airlens-models-pull")
        with mlflow.start_run(run_name=f"pull-{model}-v{entry['source_version']}") as r:
            mlflow.set_tags({"package_sha": sha, "source": entry["source"], "source_version": entry["source_version"],
                             "data_version": entry.get("data_version") or ""})
            if entry["metrics"]:
                mlflow.log_metrics({f"test_{k}": v for k, v in entry["metrics"].items()})
            if entry["kind"] == "lightgbm":
                import lightgbm as lgb
                import mlflow.lightgbm

                info = mlflow.lightgbm.log_model(lgb.Booster(model_file=str(folder / "model.lgb")), name="model")
            else:
                import mlflow.onnx
                import onnx

                info = mlflow.onnx.log_model(onnx.load(str(folder / "model.onnx")), name="model",
                                             metadata={k: meta[k] for k in ("classes", "data_version") if k in meta})
            meta["mlflow_run_id"] = r.info.run_id
            mlflow.log_dict(meta, "bundle/metadata.json")
            if (folder / "plots").exists():
                mlflow.log_artifacts(str(folder / "plots"), artifact_path="plots")
        mv = mlflow.register_model(info.model_uri, model, tags={"package_sha": sha, "source": entry["source"]})
        version, status = mv.version, "didaftarkan"
        keys = tuple(entry["metrics"]) or ("macro_f1",)
        registry.record_registration(engine, version, "candidate", {**meta, "val_metrics": entry["metrics"]},
                                     model=model, metric_keys=keys)
    alias = entry.get("alias", "production")
    if registry.alias_version(alias, model=model) != str(version):
        (registry.set_challenger if alias == "challenger" else registry.set_production)(engine, version, model=model)
    return {"model": model, "version": str(version), "alias": alias, "status": status, "source": entry["source"],
            "metrics": entry["metrics"]}


def show_active() -> None:
    from airlens.models import registry

    for m in MODELS:
        print(f"  {m:18s} production v{registry.alias_version('production', model=m) or '-'}"
              f"   challenger v{registry.alias_version('challenger', model=m) or '-'}")


# ------------------------------------------------------------------ Kaggle
def kaggle_user() -> str:
    u = os.environ.get("KAGGLE_USERNAME", "")
    if not u or not os.environ.get("KAGGLE_KEY"):
        raise SystemExit("KAGGLE_USERNAME / KAGGLE_KEY kosong di .env (kaggle.com → Settings → API).")
    return u


def kaggle(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    from airlens_trainer.kaggle_ops import explain

    p = subprocess.run(["kaggle", *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        out = (p.stdout or "") + (p.stderr or "")
        print(out.strip()[-1500:])
        raise SystemExit(f"GALAT kaggle: {explain(out)}")
    return p


def publish() -> int:
    from airlens.models import registry

    versions = {m: registry.alias_version("production", model=m) for m in MODELS}
    missing = [m for m, v in versions.items() if not v]
    if missing:
        print(f"Belum ada production untuk: {', '.join(missing)}. Latih/impor dulu.")
        return 1
    out = BUILD / "package"
    manifest = build_package(out, versions)
    print("Model yang akan diterbitkan (alias tujuan production):")
    for e in manifest["models"]:
        size = sum(f["bytes"] for f in e["files"].values()) / 2**20
        print(f"  {e['name']:18s} v{e['source_version']:>3} sumber {e['source']:7s} {'DEV ' if e['dev_model'] else ''}"
              f"metrik {e['metrics']}  ({size:.1f} MB)")
    if os.environ.get("PUBLISH_ONLY_BUILD") == "1":
        print(f"Paket dibuat di build/models/package (tidak diunggah).")
        return 0
    if os.environ.get("MODELS_APPROVED") != "1":
        print("BELUM DIUNGGAH: periksa metrik di atas. Bila setuju: make models-publish MODELS_APPROVED=1 NOTES=\"...\"")
        return 2
    u = kaggle_user()
    (out / "dataset-metadata.json").write_text(json.dumps(
        {"title": DATASET_SLUG, "id": f"{u}/{DATASET_SLUG}", "licenses": [{"name": "other"}]}, indent=2))
    notes = os.environ.get("NOTES") or ", ".join(f"{e['name']} v{e['source_version']} ({e['source']})" for e in manifest["models"])
    if kaggle("datasets", "status", f"{u}/{DATASET_SLUG}", check=False).returncode == 0:
        kaggle("datasets", "version", "-p", str(out), "-m", notes, "-r", "tar", "-q")
    else:
        kaggle("datasets", "create", "-p", str(out), "-r", "tar", "-q")
    print(f"Diterbitkan ke dataset privat {u}/{DATASET_SLUG}: {notes}")
    return 0


def pull() -> int:
    import tarfile

    from mlflow import MlflowClient

    from airlens.db.session import get_engine

    if os.environ.get("PULL_DIR"):
        root = Path(os.environ["PULL_DIR"])
    else:
        u = kaggle_user()
        dl = BUILD / "download"
        shutil.rmtree(dl, ignore_errors=True)
        dl.mkdir(parents=True)
        ref = f"{u}/{DATASET_SLUG}" + (f"/{os.environ['VERSION']}" if os.environ.get("VERSION") else "")
        kaggle("datasets", "download", ref, "-p", str(dl), "--unzip", "-q")
        for t in list(dl.rglob("*.tar")) + list(dl.rglob("*.tar.gz")):   # mode -r tar: tiap folder jadi arsip
            with tarfile.open(t) as tf:
                tf.extractall(t.parent, filter="data")
            t.unlink()
        root = next(p.parent for p in dl.rglob("manifest.json"))
    try:
        manifest = verify_package(root)
    except PackageError as exc:
        print(f"DITOLAK: {exc}")
        return 1
    print(f"Paket {manifest['created']} (commit {manifest.get('git_commit') or '-'}): sha256 semua berkas cocok")
    client, engine = MlflowClient(), get_engine()
    for e in manifest["models"]:
        r = register(e, root, client, engine)
        print(f"  {r['model']:18s} v{r['version']:>3} -> {r['alias']} ({r['status']}; sumber {r['source']}, metrik {r['metrics']})")
    print("Model aktif di mesin ini:")
    show_active()
    print("API memuat versi baru otomatis dalam ≤ 30 detik.")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    return {"publish": publish, "pull": pull}.get(cmd, lambda: print("publish|pull") or 1)()


if __name__ == "__main__":
    sys.exit(main())
