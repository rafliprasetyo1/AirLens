# syntax=docker/dockerfile:1
# Image Python untuk api, scheduler, trainer, dan tests (satu file, beda target).
# Konteks build: root repo. Dependency terkunci dengan hash (requirements/*.txt, dibuat `make lock`).
FROM python:3.12.14-slim-bookworm AS base
# Koneksi lambat: timeout panjang + percobaan ulang. Wheel di-cache oleh BuildKit (--mount=type=cache) sehingga
# tahap lain memakai ulang unduhan yang sama; cache itu tidak ikut masuk ke image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10
# UID 1000 = pengguna WSL, agar file di bind mount (./data, ./artifacts, ./results) tetap milik pengguna.
RUN useradd --create-home --uid 1000 airlens
WORKDIR /app

FROM base AS api
COPY requirements/api.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes --no-deps -r /tmp/requirements.txt
COPY src/ /app/src/
COPY config/ /app/config/
COPY api/ /app/api/
ENV PYTHONPATH=/app/src:/app/api
RUN mkdir -p /app/modelcache /app/uploads && chown airlens:airlens /app/modelcache /app/uploads
USER airlens
EXPOSE 8000
CMD ["sh", "-c", "alembic -c /app/src/airlens/db/alembic.ini upgrade head && exec uvicorn airlens_api.main:app --host 0.0.0.0 --port 8000 --workers 1"]

FROM base AS scheduler
COPY requirements/scheduler.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes --no-deps -r /tmp/requirements.txt
COPY src/ /app/src/
COPY config/ /app/config/
COPY scheduler/ /app/scheduler/
ENV PYTHONPATH=/app/src:/app/scheduler
RUN mkdir -p /app/results && chown airlens:airlens /app/results
USER airlens
CMD ["python", "-m", "airlens_scheduler.main"]

FROM base AS trainer
# unar: ekstrak arsip RAR (dataset Dhaka). Versi mengikuti image dasar Debian bookworm yang dipin.
RUN apt-get update && apt-get install -y --no-install-recommends unar && rm -rf /var/lib/apt/lists/*
COPY requirements/trainer.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes --no-deps -r /tmp/requirements.txt
# PyTorch: cpu (laptop, default) atau cu126 (lab, lewat compose.gpu.yaml). Kode tetap identik.
ARG TORCH_VARIANT=cpu
COPY requirements/torch-${TORCH_VARIANT}.txt /tmp/torch.txt
# Wheel +cpu/+cu126 hanya ada di index PyTorch; --require-hashes menjamin file sama persis dengan yang dikunci.
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes --no-deps --extra-index-url https://download.pytorch.org/whl/${TORCH_VARIANT} -r /tmp/torch.txt
ENV TORCH_HOME=/app/artifacts/torch-cache
COPY src/ /app/src/
COPY config/ /app/config/
COPY trainer/ /app/trainer/
ENV PYTHONPATH=/app/src:/app/trainer
USER airlens
CMD ["python", "-m", "airlens_trainer"]

FROM base AS dev
RUN apt-get update && apt-get install -y --no-install-recommends unar && rm -rf /var/lib/apt/lists/*
COPY requirements/dev.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes --no-deps -r /tmp/requirements.txt
COPY requirements/torch-cpu.txt /tmp/torch.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes --no-deps --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/torch.txt
COPY src/ /app/src/
COPY config/ /app/config/
COPY api/ /app/api/
COPY scheduler/ /app/scheduler/
COPY trainer/ /app/trainer/
ENV PYTHONPATH=/app/src:/app/api:/app/scheduler:/app/trainer
USER airlens
CMD ["pytest", "/app/tests", "-q", "-p", "no:cacheprovider"]
