# Build context = raiz del repo (ver docker-compose.yml): a diferencia de
# services/incidents-api/, este servicio necesita data/pipelines/ (importa
# exec_weekly_inventory_kpis via sys.path, ver pipeline_path.py) ademas de su
# propio codigo, y ambos viven fuera de services/reporting/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY services/reporting/requirements.txt ./services/reporting/requirements.txt
RUN uv pip install --system -r services/reporting/requirements.txt

COPY data/pipelines/exec_weekly_inventory_kpis ./data/pipelines/exec_weekly_inventory_kpis
COPY services/reporting/ ./services/reporting/

WORKDIR /app/services/reporting

EXPOSE 8010

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--reload"]
