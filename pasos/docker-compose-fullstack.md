# Dockerizacion full-stack local (UIS + Backend)

Este documento define la configuracion de Docker para ejecutar interfaces y backend en desarrollo con hot reload.

## Objetivo

- Levantar `website` y `backoffice` en contenedores con Next.js en puertos separados.
- Levantar `incidents-api` con Uvicorn y `--reload`.
- Conectar ambos servicios por red Docker usando nombres de servicio (sin `localhost` entre contenedores).

## Archivos creados

- `uis/Dockerfile`
- `uis/start.sh`
- `uis/.dockerignore`
- `services/Dockerfile`
- `services/.dockerignore`
- `docker-compose.yml`

## Detalles de implementacion

### 1) Interfaces: `uis/Dockerfile`

- Base: imagen oficial `node:20-alpine`.
- Instalacion separada de dependencias:
  - `website/package*.json` y `npm install` en `website/`.
  - `backoffice/package*.json` y `npm install` en `backoffice/`.
- `CMD` por defecto: `./start.sh`.

### 2) Script de arranque: `uis/start.sh`

Arranca ambas apps Next.js en paralelo:

- `website` en `0.0.0.0:3000`
- `backoffice` en `0.0.0.0:3001`

### 3) Exclusion de archivos en UIS: `uis/.dockerignore`

Se excluyen al menos:

- `node_modules`
- `.next`
- `.env*`
- `*.log`

### 4) Backend: `services/Dockerfile`

- Base: imagen oficial `python:3.12-slim`.
- Instalacion de `uv` con `pip`.
- Dependencias via:
  - `uv pip install --system -r requirements.txt`
- Arranque del API:
  - `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

### 5) Exclusion de archivos en Services: `services/.dockerignore`

Se excluyen al menos:

- `__pycache__`
- `*.pyc`
- `.env*`
- `tests/`
- `*.log`

### 6) Orquestacion: `docker-compose.yml`

Servicios definidos:

- `uis`
  - Build desde `./uis`
  - Bind mount de codigo fuente `./uis:/app`
  - Comando de desarrollo con `next dev` para ambas apps
  - Puertos publicados: `3000:3000` y `3001:3001`
  - Variables de entorno apuntando al backend por nombre de servicio:
    - `NEXT_PUBLIC_API_URL=http://backend:8000`
    - `BACKEND_URL=http://backend:8000`

- `backend`
  - Build desde `./services`
  - Bind mount de codigo fuente del repo `./:/app`
  - Working directory en `services/incidents-api` dentro del contenedor
  - Uvicorn con `--reload`
  - Puerto publicado: `8000:8000`

Red Docker explicita:

- `trackflow_network`

## URLs de acceso y conexion

Desde host:

- Website: `http://localhost:3000`
- Backoffice: `http://localhost:3001`
- Backend API: `http://localhost:8000`

Entre contenedores (interno Docker):

- Backend desde UIS: `http://backend:8000`

## Comandos de uso

Desde la raiz del monorepo:

- Levantar:
  - `docker compose up --build`
- Parar:
  - `docker compose down`

## Atajos con Makefile

Se agrego `Makefile` en la raiz para simplificar comandos diarios:

- `make help`
- `make build`
- `make up`
- `make down`
- `make restart`
- `make logs`
- `make logs-backend`
- `make logs-uis`
- `make ps`
- `make health`
- `make clean`

Chequeos de salud incluidos en `make health`:

- Backend: `http://localhost:8000/docs`
- Website: `http://localhost:3000`
- Backoffice: `http://localhost:3001`
