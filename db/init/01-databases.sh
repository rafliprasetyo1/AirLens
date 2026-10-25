#!/bin/sh
# Hanya berjalan saat volume database masih kosong (pertama kali `make up`).
# mlflow: backend store MLflow. airlens_test: database terpisah untuk pytest (test boleh merusak isinya).
set -eu
for db in mlflow airlens_test; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "CREATE DATABASE $db OWNER \"$POSTGRES_USER\";"
done
