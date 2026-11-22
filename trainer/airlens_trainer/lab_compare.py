"""Tahap lab-all `compare`: model referensi 5 kelas (TRAIN_CLASS_SCHEME=epa5) vs model tiga tingkat production pada
split test yang sama, lewat compare_merge. Bundle dicari dari artifacts/models/<data_version>/: candidates.json (model
utama) dan reference_epa5/reference.json (referensi). Keluaran: results/compare_merge_3class.json + .md."""

import json
import sys

from airlens.config import load_profile
from airlens.data.manifest import read_data_version
from airlens.data.paths import processed_dir
from airlens.models.bundle import models_dir, read_candidates


def main() -> int:
    profile = load_profile()["profile"]
    dv = read_data_version(processed_dir(profile))
    cand = read_candidates(dv)
    new = cand["models"][cand["production"]]["dir"]
    ref_file = models_dir(dv) / "reference_epa5" / "reference.json"
    if not ref_file.exists():
        print(f"referensi 5 kelas belum ada ({ref_file}); jalankan make train TRAIN_CLASS_SCHEME=epa5 dulu")
        return 1
    old = json.loads(ref_file.read_text())["bundle"]
    from airlens_trainer import compare_merge

    sys.argv = ["compare_merge", old, new]
    return compare_merge.main()


if __name__ == "__main__":
    sys.exit(main())
