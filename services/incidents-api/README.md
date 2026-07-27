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

- `POST /api/incidents/analyze`
- Content type: `multipart/form-data`
- Form field name: `file`
- Accepted file: `.csv`

Example with curl:

```bash
curl -X POST "http://localhost:8000/api/incidents/analyze" \
  -F "file=@/tmp/incidents-context-valid.csv"
```

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

## Password reset flow

- `POST /auth/forgot-password` — `{ email }`. Always returns `200`; never reveals whether the email exists.
- `POST /auth/reset-password` — `{ token, new_password }`. Validates the signed, short-lived, single-use token from the email link.
- `POST /auth/change-password` — `{ current_password, new_password }`, requires a `Bearer` access token. Verifies the current password before updating.
