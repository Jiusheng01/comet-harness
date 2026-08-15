#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Preparing Comet Harness Codespace"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Docker Compose reads the root .env. Keep checked-in examples immutable.
if [ ! -f .env ]; then
  cp .env.example .env
fi

if [ ! -f api/.env ]; then
  cp api/.env.example api/.env
fi

# Replace placeholder development secrets once. Do not overwrite user-provided values.
JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
FERNET_KEY="$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"

python3 - "$JWT_SECRET" "$FERNET_KEY" <<'PY'
from pathlib import Path
import sys

jwt_secret, fernet_key = sys.argv[1:]
for filename in (Path('.env'), Path('api/.env')):
    text = filename.read_text()
    text = text.replace('JWT_SECRET=change-me-in-production', f'JWT_SECRET={jwt_secret}')
    text = text.replace('FERNET_KEY=change-me-fernet-key', f'FERNET_KEY={fernet_key}')
    filename.write_text(text)
PY

echo "==> Installing backend dependencies"
(
  cd api
  uv sync
)

echo "==> Installing frontend dependencies"
(
  cd web
  npm install
)

echo "==> Building Elasticsearch image"
docker compose build elasticsearch

echo "==> Starting development storage services"
docker compose up -d postgres elasticsearch neo4j redis

echo "==> Waiting for PostgreSQL"
for _ in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-comet}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Waiting for Elasticsearch and Neo4j"
for service in elasticsearch neo4j; do
  for _ in $(seq 1 90); do
    status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "comet-${service/elasticsearch/es}" 2>/dev/null || true)"
    if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
      break
    fi
    sleep 2
  done
done

echo "==> Running database migrations"
(
  cd api
  uv run alembic upgrade head
)

cat <<'EOF'

Comet Harness Codespace is prepared.

Start the backend:
  cd api && uv run python run.py

Start Celery worker (another terminal):
  cd api && uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory,beat,research --pool=threads

Start the frontend (another terminal):
  cd web && npm run dev -- --host 0.0.0.0

Storage status:
  docker compose ps
EOF
