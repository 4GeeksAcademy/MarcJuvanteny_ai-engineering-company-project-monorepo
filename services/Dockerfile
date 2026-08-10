FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/incidents-api

RUN pip install --no-cache-dir uv

COPY incidents-api/requirements.txt ./requirements.txt
RUN uv pip install --system -r requirements.txt

COPY incidents-api/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
