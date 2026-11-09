#!/usr/bin/env bash
# Arranca el backoffice en local (pensado para GitHub Codespaces):
#   1. Contenedores de demo: Postgres (5433), Redis (6379), Qdrant (6333)
#   2. incidents-api en :8001, knowledge-api en :8020 y worker de Celery
#      (en segundo plano)
#   3. Backoffice Next.js en :3000 (en primer plano; Ctrl+C lo para)
#
# El navegador solo necesita el puerto 3000: uis/backoffice/.env.local usa el
# proxy de next.config.ts (/backend -> :8001, /knowledge-backend -> :8020).
#
# Uso: bash scripts/dev-backoffice.sh
# Logs de las APIs: /tmp/trackflow-incidents-api.log y /tmp/trackflow-knowledge-api.log
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Contenedores de demo"
docker start tf-demo-pg tf-demo-redis tf-demo-qdrant >/dev/null
for _ in $(seq 1 30); do
  docker exec tf-demo-pg pg_isready -q && break
  sleep 1
done

start_api() { # nombre carpeta puerto
  local name="$1" dir="$ROOT/services/$2" port="$3"
  if ss -ltn | grep -q ":$port "; then
    echo "==> $name ya escucha en :$port"
    return
  fi
  echo "==> Arrancando $name en :$port"
  (cd "$dir" && nohup .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port "$port" \
    >"/tmp/trackflow-$name.log" 2>&1 &)
  for _ in $(seq 1 60); do
    curl -fsS -m2 -o /dev/null "http://localhost:$port/docs" && { echo "    OK"; return; }
    sleep 1
  done
  echo "    ERROR: $name no responde. Revisa /tmp/trackflow-$name.log" >&2
  exit 1
}

start_api incidents-api incidents-api 8001
start_api knowledge-api knowledge-api 8020

# Worker de Celery: procesa en segundo plano las RFPs subidas y el analisis
# de incidencias por CSV. Sin el, los tickets se quedan en "Analizando...".
if pgrep -f "[c]elery -A celery_app worker" >/dev/null; then
  echo "==> Worker de Celery ya en marcha"
else
  echo "==> Arrancando worker de Celery"
  (cd "$ROOT/services/incidents-api" && nohup .venv/bin/celery -A celery_app worker --loglevel=info \
    >/tmp/trackflow-celery-worker.log 2>&1 &)
  for _ in $(seq 1 30); do
    grep -q "ready\." /tmp/trackflow-celery-worker.log 2>/dev/null && { echo "    OK"; break; }
    sleep 1
  done
  grep -q "ready\." /tmp/trackflow-celery-worker.log 2>/dev/null \
    || echo "    AVISO: el worker no confirmo arranque. Revisa /tmp/trackflow-celery-worker.log" >&2
fi

echo "==> Backoffice en http://localhost:3000 (Ctrl+C para parar)"
cd "$ROOT/uis/backoffice"
exec npm run dev
