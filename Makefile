# AirLens — perintah umum. Semua target menerima PROFILE=laptop|lab (default: laptop).
PROFILE ?= laptop
ifeq ($(filter $(PROFILE),laptop lab),)
$(error PROFILE harus laptop atau lab, bukan '$(PROFILE)')
endif
export APP_PROFILE := $(PROFILE)
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
.PHONY: help setup-check env-check up down ps logs test ui-test docs-check lock drift-sim \
	data train eval retrain promote rollback monitor lab-all export-results

help:
	@echo "Target: setup-check up down ps logs test lock data train eval retrain promote rollback monitor lab-all export-results"
	@echo "Contoh: make up PROFILE=laptop"

setup-check:
	@scripts/setup_check.sh $(PROFILE)

env-check:
	@test -f .env || { echo "File .env belum ada. Jalankan: cp .env.example .env lalu isi nilainya."; exit 1; }

up: env-check
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

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
train: env-check
	@mkdir -p artifacts results
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.train

eval: env-check
	@mkdir -p artifacts results
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.eval
# Fase 5. Monitoring = job yang sama dengan job terjadwal di layanan scheduler.
monitor:
	$(COMPOSE) exec -T scheduler python -m airlens_scheduler.monitor $(if $(SINCE),--since $(SINCE)) $(if $(UNTIL),--until $(UNTIL))

retrain: env-check
	@mkdir -p artifacts results
	$(COMPOSE) --profile train run --rm --build -e REGISTER_ALIAS=challenger trainer python -m airlens_trainer.train

promote: env-check
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.promote

rollback: env-check
	$(COMPOSE) --profile train run --rm --build $(if $(VERSION),-e VERSION=$(VERSION)) trainer python -m airlens_trainer.rollback

drift-sim: env-check
	$(COMPOSE) --profile train run --rm --build trainer python -m airlens_trainer.drift_sim
lab-all export-results:
	@echo "belum tersedia, lihat Fase 6"
