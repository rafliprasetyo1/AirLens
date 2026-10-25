FROM python:3.12.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements/mlflow.txt /tmp/requirements.txt
RUN pip install --require-hashes --no-deps -r /tmp/requirements.txt
RUN useradd --create-home --uid 1000 mlflow && mkdir /mlartifacts && chown mlflow:mlflow /mlartifacts
USER mlflow
EXPOSE 5000
