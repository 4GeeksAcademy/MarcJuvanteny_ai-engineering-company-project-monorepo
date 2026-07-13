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
