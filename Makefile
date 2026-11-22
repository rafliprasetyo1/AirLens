# AirLens — perintah umum. Semua target menerima PROFILE=laptop|lab (default: laptop).
PROFILE ?= laptop
ifeq ($(filter $(PROFILE),laptop lab),)
$(error PROFILE harus laptop atau lab, bukan '$(PROFILE)')
endif
export APP_PROFILE := $(PROFILE)
empty :=
space := $(empty) $(empty)
comma := ,
# Dicatat di MLflow. Tanpa commit, run tetap bisa dilacak lewat code_version (hash isi kode).
# SMOKE=1: uji asap alur (1 epoch, satu arsitektur). Hasilnya ditandai, BUKAN hasil evaluasi.
export AIRLENS_SMOKE := $(if $(filter 1,$(SMOKE)),1,0)
export GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo belum-ada-commit)$(shell git diff --quiet HEAD 2>/dev/null || echo -dirty)

COMPOSE := docker compose -f compose.yaml
ifeq ($(PROFILE),lab)
COMPOSE += -f compose.gpu.yaml
endif

# Penguncian dependency: dijalankan di container, dengan batas tanggal rilis agar hasilnya reproducible.
UV_IMAGE  := ghcr.io/astral-sh/uv:0.9.5-python3.12-bookworm-slim
LOCK_DATE := 2026-10-10T00:00:00Z
UV_COMPILE := uv pip compile --quiet --generate-hashes --python-version 3.12 \
	--exclude-newer $(LOCK_DATE) --custom-compile-command "make lock"

.DEFAULT_GOAL := help
.PHONY: help setup-check env-check up down ps logs test ui-test docs-check lock drift-sim migrate \
	data train eval retrain promote rollback monitor lab-all export-results sync-modules \
	data-beta train-beta promote-beta rollback-beta firmware-beta \
	import-beta-recordings beta-recordings-push import-results compare-merge vapid-keys kaggle-push kaggle-status kaggle-pull \
	models-publish models-pull expo-public expo-public-stop tokens doctor expo-setup gladi gladi-stop

help:
	@echo "Target: setup-check up down ps logs test ui-test docs-check lock data train eval retrain promote rollback monitor drift-sim lab-all export-results sync-modules data-beta train-beta promote-beta rollback-beta firmware-beta import-beta-recordings beta-recordings-push import-results compare-merge vapid-keys kaggle-push kaggle-status kaggle-pull models-publish models-pull expo-public expo-public-stop tokens doctor expo-setup gladi gladi-stop"
	@echo "Contoh: make up PROFILE=laptop"

setup-check:
	@scripts/setup_check.sh $(PROFILE)

env-check:
	@test -f .env || { echo "File .env belum ada. Jalankan: cp .env.example .env lalu isi nilainya."; exit 1; }

up: env-check
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

# Salin modul perakitan docs/modules/ -> web/static/modules/ (tanpa tautan Google Fonts).
sync-modules:
	@bash scripts/sync_modules.sh

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

test: env-check
	@mkdir -p data/processed
	$(COMPOSE) --profile test run --rm --build tests

# Uji UI di Chrome headless (butuh `make up` dan `make data`). Tangkapan layar + laporan: results/ui/.
UI_IMAGE := zenika/alpine-chrome:124-with-puppeteer
ui-test:
	@mkdir -p results/ui/fixtures
	$(COMPOSE) --profile train run --rm --no-deps -v "$(CURDIR)/tests/ui:/app/tests/ui:ro" -v "$(CURDIR)/results/ui:/app/results/ui" \
		trainer python /app/tests/ui/make_fixtures.py /app/results/ui/fixtures
	docker run --rm --network airlens_default --cap-add=SYS_ADMIN -e BASE_URL=http://web \
		-v "$(CURDIR)/tests/ui:/usr/src/app/tests:ro" -v "$(CURDIR)/results/ui/fixtures:/fixtures:ro" \
		-v "$(CURDIR)/results/ui:/out" -w /usr/src/app --user root $(UI_IMAGE) node tests/ui_check.js

# Validasi diagram Mermaid di ARCHITECTURE.md (render di Chrome headless).
docs-check:
	@mkdir -p results/ui
	docker run --rm --cap-add=SYS_ADMIN -v "$(CURDIR)/ARCHITECTURE.md:/doc/ARCHITECTURE.md:ro" \
		-v "$(CURDIR)/tests/ui:/usr/src/app/tests:ro" -v "$(CURDIR)/results/ui:/out" -w /usr/src/app --user root \
		$(UI_IMAGE) node tests/render_mermaid.js

lock:
	docker run --rm -u $$(id -u):$$(id -g) -e UV_CACHE_DIR=/tmp/uv-cache \
		-v "$(CURDIR)/requirements:/req" -w /req $(UV_IMAGE) sh -euc '\
		$(UV_COMPILE) dev.in -o dev.txt; \
		for f in api scheduler trainer; do $(UV_COMPILE) -c dev.txt $$f.in -o $$f.txt; done; \
		$(UV_COMPILE) mlflow.in -o mlflow.txt; \
		for v in cpu cu126; do $(subst --exclude-newer $(LOCK_DATE),,$(UV_COMPILE)) -c trainer.txt --index-strategy unsafe-best-match \
			--extra-index-url https://download.pytorch.org/whl/$$v torch-$$v.in -o torch-$$v.txt; done'

data: env-check
	@mkdir -p data results
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens.data.pipeline
	$(if $(SKIP_BETA_DATA),,$(COMPOSE) --profile train run --rm trainer python -m airlens.data.beta_gas)

# Model gas Beta (revisi Beta SHAP): MultimodalGasData (CC BY 4.0, CSV 330 KB) -> LightGBM 4 kelas + SHAP.
# Ringan di CPU (hitungan detik) untuk semua profil. config/beta_gas.yaml
data-beta: env-check
	@mkdir -p data results
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens.data.beta_gas

train-beta: env-check migrate
	@mkdir -p artifacts results
	$(COMPOSE) --profile train run --rm --build $(if $(REGISTER_ALIAS),-e REGISTER_ALIAS=$(REGISTER_ALIAS)) trainer python -m airlens_trainer.train_beta

promote-beta: env-check migrate
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.promote_beta

rollback-beta: env-check migrate
	$(COMPOSE) --profile train run --rm --build -e MODEL=airlens-beta-gas $(if $(VERSION),-e VERSION=$(VERSION)) trainer python -m airlens_trainer.rollback

# Rekaman alat Beta sendiri (tools/recorder.html). Di laptop HANYA evaluasi (domain shift), tanpa pelatihan.
# CSV boleh beberapa, dipisah koma. Contoh: make import-beta-recordings CSV=~/Downloads/airlens_beta_recording.csv
import-beta-recordings: env-check migrate
	@test -n "$(CSV)" || { echo "Pakai: make import-beta-recordings CSV=<path ke CSV recorder>"; exit 1; }
	@mkdir -p data/raw/beta_recordings results
	@for f in $(subst $(comma), ,$(CSV)); do cp "$$f" data/raw/beta_recordings/; done
	$(COMPOSE) --profile train run --rm --build \
		-e CSVS="$(subst $(space),$(comma),$(foreach f,$(subst $(comma), ,$(CSV)),/app/data/raw/beta_recordings/$(notdir $(f))))" \
		trainer python -m airlens_trainer.import_beta_recordings

# Latih ulang model Beta dengan rekaman sendiri DI KAGGLE: unggah CSV sebagai dataset privat airlens-beta-recordings,
# lalu make kaggle-push (kernel memakainya otomatis bila ada).
beta-recordings-push: env-check
	@test -n "$(CSV)" || { echo "Pakai: make beta-recordings-push CSV=<path CSV recorder>[,<CSV lain>]"; exit 1; }
	@mkdir -p build/kaggle/recordings
	@for f in $(subst $(comma), ,$(CSV)); do cp "$$f" build/kaggle/recordings/; done
	scripts/kaggle.sh recordings

# Firmware Beta (ESP32 + 4 MQ): arduino-cli di laptop -> web/static/tools/firmware/beta.bin.
firmware-beta:
	scripts/firmware_build.sh
# Skema database aplikasi (Alembic, idempoten). Dulu hanya dijalankan api saat start; di lab yang baru (tanpa
# `make up`) tabel model_versions belum ada sehingga train gagal. Ditemukan lewat simulasi klon bersih.
migrate: env-check
	$(COMPOSE) --profile train run --rm --build trainer alembic -c /app/src/airlens/db/alembic.ini upgrade head

# TRAIN_CLASS_SCHEME=epa5 = model referensi 5 kelas untuk compare_merge (tanpa alias); TRAIN_MODELS=a,b membatasi arsitektur
train: env-check migrate
	@mkdir -p artifacts results
	$(COMPOSE) --profile train run --rm --build $(if $(TRAIN_CLASS_SCHEME),-e TRAIN_CLASS_SCHEME=$(TRAIN_CLASS_SCHEME)) \
		$(if $(TRAIN_MODELS),-e TRAIN_MODELS=$(TRAIN_MODELS)) trainer python -m airlens_trainer.train

# Arsip hasil lab/Kaggle -> MLflow laptop (airlens-aqi, airlens-beta-gas), alias ALIAS (bawaan challenger; production setelah disetujui).
# CONFIRM=1 bila alias challenger yang ada boleh dipindah tanpa ditanya.
import-results: env-check migrate
	@test -f "$(ARCHIVE)" || { echo "Pakai: make import-results ARCHIVE=<path airlens_results_*.tar.gz>"; exit 1; }
	@mkdir -p data/import results
	@cp -n "$(ARCHIVE)" data/import/ 2>/dev/null || true
	$(COMPOSE) --profile train run --rm --build -e ARCHIVE=/app/data/import/$(notdir $(ARCHIVE)) \
		$(if $(CONFIRM),-e CONFIRM=$(CONFIRM)) $(if $(ALIAS),-e ALIAS=$(ALIAS)) trainer python -m airlens_trainer.import_results

# Pelatihan di Kaggle Notebook (prompt 7): push kode + kernel, pantau, unduh arsip hasil (format sama dengan lab).
kaggle-push: env-check
	scripts/kaggle.sh push
kaggle-status: env-check
	scripts/kaggle.sh status
kaggle-pull: env-check
	scripts/kaggle.sh pull

# Paket model final -> dataset Kaggle privat airlens-models (unggah hanya dengan MODELS_APPROVED=1), dan sebaliknya
# di mesin mana pun: unduh, periksa sha256, impor ke MLflow, pasang alias. Aman diulang.
models-publish: env-check
	@mkdir -p build/models
	$(COMPOSE) --profile train run --rm --build -T -v "$(CURDIR)/build/models:/models_build" \
		$(if $(MODELS_APPROVED),-e MODELS_APPROVED=$(MODELS_APPROVED)) $(if $(NOTES),-e NOTES="$(NOTES)") \
		$(if $(PUBLISH_ONLY_BUILD),-e PUBLISH_ONLY_BUILD=1) trainer python -m airlens_trainer.models_dist publish
models-pull: env-check migrate
	@mkdir -p build/models
	$(COMPOSE) --profile train run --rm --build -T -v "$(CURDIR)/build/models:/models_build" \
		$(if $(VERSION),-e VERSION=$(VERSION)) $(if $(PULL_DIR),-e PULL_DIR=$(PULL_DIR)) \
		trainer python -m airlens_trainer.models_dist pull

# Kesiapan mesin (sama di laptop dan lab) dan satu perintah hari pameran.
doctor:
	@scripts/doctor.sh
expo-setup:
	scripts/expo_setup.sh

# Token sensor/node acak ke .env bila kosong (wajib di mode expo); tidak dicetak.
tokens:
	ROTATE=$(ROTATE) scripts/tokens.sh

# Gladi tanpa alat (Wokwi -> ngrok -> AirLens), kapan saja. Butuh ngrok menyala (make expo-public / expo-setup).
gladi:
	scripts/gladi.sh start
gladi-stop:
	KEEP_TOKENS=$(KEEP_TOKENS) scripts/gladi.sh stop

# ngrok (akun free: domain acak per sesi, disimpan/ditimpa ke NGROK_DOMAIN di .env). Lihat docs/EXPO.md.
expo-public: env-check
	scripts/expo_public.sh
expo-public-stop:
	scripts/expo_public.sh stop

# Web Push: kunci VAPID ke .env (sekali; tidak dicetak, tidak menimpa kunci yang ada)
vapid-keys:
	scripts/vapid_keys.sh

# Perbandingan adil 5 vs 3 kelas pada test yang sama (butuh model referensi: make train TRAIN_CLASS_SCHEME=epa5)
compare-merge: env-check
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.lab_compare

eval: env-check
	@mkdir -p artifacts results
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.eval
# Fase 5. Monitoring = job yang sama dengan job terjadwal di layanan scheduler.
monitor:
	$(COMPOSE) exec -T scheduler python -m airlens_scheduler.monitor $(if $(SINCE),--since $(SINCE)) $(if $(UNTIL),--until $(UNTIL))

retrain: env-check migrate
	@mkdir -p artifacts results
	$(COMPOSE) --profile train run --rm --build -e REGISTER_ALIAS=challenger trainer python -m airlens_trainer.train

promote: env-check migrate
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.promote

rollback: env-check migrate
	$(COMPOSE) --profile train run --rm --build $(if $(VERSION),-e VERSION=$(VERSION)) trainer python -m airlens_trainer.rollback

drift-sim: env-check migrate
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.drift_sim
# Fase 6. Satu perintah untuk lab: cek -> data -> latih -> evaluasi -> kemas hasil (durasi tiap tahap dicatat di logs/).
lab-all: env-check
	@mkdir -p data artifacts results logs
	SMOKE=$(if $(filter 1,$(SMOKE)),1,0) scripts/lab_all.sh $(PROFILE)

# Arsip bertanggal: results/, model, log, volume artefak MLflow, dump database mlflow + airlens. Tanpa .env.
export-results: env-check
	scripts/export_results.sh $(PROFILE)
