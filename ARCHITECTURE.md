# Arsitektur AirLens

Diagram ini menggambarkan sistem **sebagaimana kodenya sekarang** (Fase S–5). Garis putus-putus menandai komponen
opsional (LM Studio). Port host: web 8080, api 8000, mlflow 5000; db tidak dibuka ke host.

## 1. Pipeline: dari pengambilan data sampai model di-serve

Setiap kotak menyebut file kode yang mengerjakannya dan keluarannya. Dijalankan berurutan oleh
`make data` → `make train` → `make eval` (layanan `trainer`), lalu disajikan oleh layanan `api` dan `web`.

```mermaid
flowchart TB
    subgraph S1["① Pengambilan data (make data)"]
        direction LR
        dl["download.py<br/>HF (sha256) · Kaggle (CRC + sha256) · Zenodo (md5)<br/>resume bila terputus"]
        raw[("data/raw/&lt;sumber&gt;/")]
        dl --> raw
    end

    subgraph S2["② Preprocessing (make data)"]
        direction LR
        norm["sources.py<br/>skema seragam · PM2.5 → kategori EPA 2024<br/>(aqi.py)"]
        qual["quality.py<br/>rusak · kecil · gelap · terang · langit"]
        dedup["dedup.py<br/>sha256 + pHash/dHash<br/>union-find"]
        split["split.py<br/>kelompok lokasi 25 km<br/>stratifikasi · Dhaka = test"]
        man["manifest.py<br/>sha256 tiap file<br/>→ data_version"]
        norm --> qual --> dedup --> split --> man
    end
    proc[("data/processed/&lt;profil&gt;/<br/>dataset.parquet · manifest.csv · report.json")]

    subgraph S3["③ Training (make train)"]
        direction LR
        feat["features/haze.py<br/>dark channel · kontras · saturasi · entropi"]
        base["baseline.py<br/>mayoritas · logreg · GBM"]
        prep["models/preprocess.py<br/>resize 224×224 utuh · normalisasi"]
        cnn["cnn.py<br/>MobileNetV3 · EfficientNet-B0<br/>augmentasi geometris saja"]
        cal["calibration.py<br/>temperature scaling + ambang 'belum pasti'<br/>HANYA di validasi"]
        onnx["cnn.export_onnx<br/>verifikasi ONNX = PyTorch"]
        feat --> base --> cal
        prep --> cnn --> cal
        cnn --> onnx
    end
    reg[("MLflow<br/>run: param · metrik · artefak · data_version · code_version<br/>registry: airlens-aqi @production")]
    bundle[("artifacts/models/&lt;data_version&gt;/<br/>model.onnx · metadata.json · candidates.json")]

    subgraph S4["④ Evaluasi (make eval)"]
        direction LR
        ev["eval.py<br/>test lewat ONNX (sama dgn API)"]
        met["metrics.py<br/>balanced acc · macro-F1 · recall<br/>ECE · risiko-cakupan"]
        plt["plots.py<br/>confusion matrix · reliability"]
        vlm["vlm.py<br/>Qwen2.5-VL via LM Studio<br/>(opsional, dilewati bila mati)"]
        ev --> met --> plt
        ev -.-> vlm
    end
    res[("results/eval_&lt;tanggal&gt;.csv + grafik")]

    subgraph S5["⑤ Serving (make up)"]
        direction LR
        store["model_store.py<br/>muat @production · cache<br/>reload otomatis bila alias pindah"]
        val["validation.py<br/>≤ 10 MB · tipe dari isi · hapus EXIF/GPS"]
        pipe["pipeline.py<br/>periksa → analisis → IQAir<br/>event SSE per tahap"]
        main["main.py<br/>POST /predict · GET /jobs/{id}/events"]
        web["web (nginx)<br/>index.html · app.js"]
        web --> main --> val --> pipe
        store --> pipe
    end
    logdb[("PostgreSQL<br/>predictions · iqair_readings · iqair_requests")]

    raw --> norm
    man --> proc
    proc --> feat
    proc --> prep
    cal --> reg
    onnx --> bundle
    onnx --> reg
    bundle --> ev
    proc --> ev
    plt --> res
    reg -- "airlens-aqi@production" --> store
    pipe --> logdb
```

## 2. Komponen dan layanan

```mermaid
flowchart LR
    user(["Pengguna<br/>(browser)"])

    subgraph windows["Windows (di luar compose)"]
        lmstudio["LM Studio<br/>Qwen2.5-VL<br/>(opsional)"]
    end

    subgraph ext["Layanan eksternal"]
        iqair["IQAir API<br/>AQI kota real-time"]
        sources["Sumber data publik<br/>PM25Vision (HF) · India–Nepal (Kaggle)<br/>Dhaka (Zenodo)"]
    end

    subgraph compose["docker compose (WSL)"]
        web["web<br/>nginx + HTML/CSS/JS<br/>:8080"]
        api["api<br/>FastAPI + onnxruntime<br/>:8000"]
        db[("db<br/>PostgreSQL<br/>airlens · mlflow · airlens_test")]
        mlflow["mlflow<br/>tracking + registry<br/>:5000"]
        trainer["trainer<br/>(profil train)<br/>data · latih · evaluasi"]
        scheduler["scheduler<br/>APScheduler<br/>heartbeat + monitoring mingguan"]
        monitor["job monitoring<br/>drift (PSI+KS, embedding) · keyakinan<br/>selisih IQAir · shadow"]
    end

    subgraph storage["Penyimpanan (di luar image)"]
        data[("./data<br/>raw · images · processed<br/>manifest + data_version")]
        artifacts[("./artifacts<br/>bundle model · cache fitur")]
        mlart[("volume mlartifacts")]
        modelcache[("volume modelcache")]
        uploads[("volume uploads<br/>hanya dengan persetujuan")]
    end

    user -- "unggah foto · kota/lokasi" --> web
    web -- "/api/* (SSE tanpa buffering)" --> api
    api -- "log prediksi · cache IQAir · kuota" --> db
    api -- "unduh airlens-aqi@production" --> mlflow
    api --> modelcache
    api --> uploads
    api -- "pembanding (cache 15 mnt, 5/mnt, 500/hari)" --> iqair

    sources -- "unduh + checksum" --> trainer
    trainer --> data
    trainer --> artifacts
    trainer -- "param · metrik · artefak<br/>data_version · code_version" --> mlflow
    trainer -. "pembanding zero-shot<br/>(dilewati bila mati)" .-> lmstudio
    mlflow --> db
    mlflow --> mlart

    scheduler -- "heartbeat" --> db
    scheduler --> monitor
    monitor -- "baca predictions<br/>tulis monitoring_reports" --> db
    monitor -. "rekomendasi retrain<br/>(make retrain oleh manusia)" .-> trainer

    classDef planned stroke-dasharray: 5 5,fill:#f6f6f3,color:#4d4c48
    classDef optional stroke-dasharray: 3 3
    class lmstudio optional
```

## 3. Alur satu prediksi (`POST /predict`)

Setiap tahap mengirim event Server-Sent Events saat **benar-benar** terjadi di pipeline (tidak ada timer palsu).

```mermaid
sequenceDiagram
    autonumber
    actor U as Pengguna
    participant W as web (nginx)
    participant A as api (FastAPI)
    participant P as pipeline (thread latar)
    participant M as model ONNX
    participant I as IQAir
    participant D as db

    U->>W: unggah foto + kota/lokasi + persetujuan
    W->>A: POST /api/predict
    A-->>U: 202 {job_id}
    U->>W: GET /api/jobs/{id}/events (SSE)
    A->>P: jalankan job

    Note over P: periksa: ukuran ≤ 10 MB, tipe dari isi file,<br/>hapus EXIF/GPS, cek gelap/terang/langit
    alt foto ditolak
        P->>D: catat (status rejected + alasan)
        P-->>U: event periksa: gagal → hasil: rejected
    else foto lolos
        P-->>U: event periksa: selesai
        P->>M: praproses 224×224 → logits
        Note over P: temperature scaling → keyakinan<br/>< ambang validasi ⇒ "belum pasti"<br/>petunjuk visual vs data latih
        P-->>U: event analisis: selesai
        P->>I: AQI kota (bila tidak ada di cache)
        alt IQAir gagal / kuota habis
            P-->>U: event iqair: gagal (prediksi tetap lanjut)
        else
            P-->>U: event iqair: selesai
        end
        P->>D: catat versi model, data_version, probabilitas,<br/>statistik input, hash foto, nilai IQAir, latensi
        P-->>U: event hasil: ok / uncertain
    end
```

## 4. Siklus model (MLOps)

```mermaid
flowchart LR
    A["make data<br/>dedup · filter · split lokasi<br/>manifest → data_version"] --> B["make train<br/>baseline + CNN<br/>kalibrasi & ambang di val"]
    B --> C["MLflow registry<br/>airlens-aqi vN"]
    C -- "alias production" --> D["api memuat ulang<br/>otomatis (≤ 30 dtk)"]
    D --> E["predictions di db"]
    E --> F["make monitor / jadwal mingguan<br/>drift · keyakinan · selisih IQAir"]
    F -- "rekomendasi" --> G["make retrain → challenger<br/>shadow mode di API"]
    G --> P["make promote<br/>test tetap + data shadow + kriteria"]
    P -- "alias production" --> C
    C -. "make rollback" .-> C
    B --> H["make eval<br/>test via ONNX<br/>results/eval_tanggal.csv"]

```

## Catatan

- **Laptop vs lab:** kode identik; perbedaan hanya lewat `APP_PROFILE` (`config/laptop.yaml` / `config/lab.yaml`) dan
  `compose.gpu.yaml` (trainer dengan PyTorch CUDA 12.6 dan GPU NVIDIA).
- **Test:** layanan `tests` (profil `test`) menjalankan pytest terhadap database `airlens_test`; `make ui-test`
  menjalankan Chrome headless terhadap layanan `web`.
- Keputusan dan alasannya: `DECISIONS.md`. Data, lisensi, dan batasan: `DATA_CARD.md`.
