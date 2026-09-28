# Build context = raiz del repo (ver docker-compose.yml): este servicio
# necesita tanto data/pipelines/ (rag.py, Fase 2) como data/process/ (rag.py,
# Fase 1 -- cargado por importlib desde el de pipelines) ademas de su propio
# codigo -- mismo patron que services/reporting/Dockerfile.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY services/knowledge-api/requirements.txt ./services/knowledge-api/requirements.txt
RUN uv pip install --system -r services/knowledge-api/requirements.txt

COPY data/process/rag.py ./data/process/rag.py
COPY data/pipelines/rag.py ./data/pipelines/rag.py
COPY services/knowledge-api/ ./services/knowledge-api/

WORKDIR /app/services/knowledge-api

EXPOSE 8020

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020", "--reload"]
