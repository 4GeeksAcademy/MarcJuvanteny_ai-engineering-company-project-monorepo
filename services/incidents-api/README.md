# incidents-api

Minimal FastAPI backend service for incident CSV analysis.

## Run locally

```bash
cd services/incidents-api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoint

- `POST /api/incidents/analyze` — enqueues the CSV analysis as a Celery
  background task instead of running it inline. Requires auth (`Bearer`
  token). Content type: `multipart/form-data`, form field name: `file`,
  accepted file: `.csv`. Returns `202 Accepted` immediately with
  `{ "task_id": "..." }` — it does **not** wait for the analysis to finish.
- `GET /tasks/{task_id}` — poll the task's status:
  `{ "task_id": ..., "status": "pending" | "started" | "success" | "failure", "result": {...} | null }`.
  `result` is only populated once `status` is `"success"`.
- `GET /api/incidents/results/export?task_id=...` — downloads the finished
  analysis as CSV. `404` if that `task_id` hasn't finished successfully yet.

Example with curl:

```bash
TASK_ID=$(curl -s -X POST "http://localhost:8000/api/incidents/analyze" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/incidents-context-valid.csv" | python3 -c "import json,sys; print(json.load(sys.stdin)['task_id'])")

curl "http://localhost:8000/tasks/$TASK_ID" -H "Authorization: Bearer $TOKEN"
```

### Background worker (Celery + Redis)

The heavy part of `/api/incidents/analyze` (parsing + validating + aggregating
the whole CSV — the highest-cost endpoint in
`Pasos/analisis-endpoints-fastapi-coste-frecuencia.md`) runs in a **separate
Celery worker process**, never inside the FastAPI process (no
`APScheduler`/`@repeat_every`/`lifespan` hook — see `tasks.py`/`celery_app.py`
for why). It needs Redis as broker + result backend.

**Via docker-compose (recommended)** — from the repo root:

```bash
docker compose up redis worker backend   # start
docker compose up -d redis worker backend flower  # + Flower monitoring, detached
docker compose stop worker               # stop just the worker
docker compose down                      # stop everything
```

Flower (task monitoring UI) is at `http://localhost:5555` once the `flower`
service is running — shows queued/running/completed tasks and active workers.

**Running the worker locally without docker** (needs a local Redis, e.g.
`docker run -p 6379:6379 redis:7-alpine`):

```bash
cd services/incidents-api
source .venv/bin/activate
celery -A celery_app worker --loglevel=info   # start (foreground; Ctrl+C to stop)
```

Failed tasks that exhaust their retries (`max_retries=3`, exponential
backoff) are logged to the `task_dlq` table in `suppliers.json`
(`task_id`, `attempt`, `error`, `timestamp` — see `task_dlq.py`) instead of
disappearing silently.

## Environment variables

Copy `.env.example` to `.env` and fill in the values. `.env` is loaded automatically at startup.

| Variable                      | Purpose                                                                                       |
| ------------------------------ | ---------------------------------------------------------------------------------------------- |
| `JWT_SECRET_KEY`               | Signs login access tokens and password-reset tokens.                                           |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | Login session lifetime, in minutes.                                                            |
| `RESET_TOKEN_EXPIRE_MINUTES`   | Password-reset link lifetime, in minutes (must be between 15 and 60).                          |
| `RESEND_API_KEY`               | API key for the [Resend](https://resend.com) transactional email service used to send password-reset emails. Never commit a real key — if unset, the reset link is logged to the console instead, for local development. |
| `EMAIL_FROM`                   | "From" address used when sending transactional emails.                                        |
| `BACKOFFICE_APP_URL`           | Base URL of the backoffice frontend, used to build the `/reset-password?token=...` link.       |
| `REDIS_URL`                    | Celery broker + result backend (e.g. `redis://localhost:6379/0`). Required to run the API (enqueues tasks) and the worker (executes them). |

## Password reset flow

- `POST /auth/forgot-password` — `{ email }`. Always returns `200`; never reveals whether the email exists.
- `POST /auth/reset-password` — `{ token, new_password }`. Validates the signed, short-lived, single-use token from the email link.
- `POST /auth/change-password` — `{ current_password, new_password }`, requires a `Bearer` access token. Verifies the current password before updating.
