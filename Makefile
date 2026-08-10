.PHONY: help build up down restart logs logs-backend logs-uis ps clean health health-backend health-website health-backoffice

COMPOSE ?= docker compose

help:
	@echo "Targets disponibles:"
	@echo "  make build    - Construir imagenes"
	@echo "  make up       - Levantar servicios en segundo plano"
	@echo "  make down     - Parar y eliminar servicios"
	@echo "  make restart  - Reiniciar entorno completo"
	@echo "  make logs     - Ver logs de todos los servicios"
	@echo "  make logs-backend   - Ver logs solo del backend"
	@echo "  make logs-uis       - Ver logs solo de interfaces"
	@echo "  make ps       - Ver estado de servicios"
	@echo "  make health   - Comprobar salud de backend y UIs"
	@echo "  make clean    - Down + borrar volumenes"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f --tail=120

logs-backend:
	$(COMPOSE) logs -f --tail=120 backend

logs-uis:
	$(COMPOSE) logs -f --tail=120 uis

ps:
	$(COMPOSE) ps

clean:
	$(COMPOSE) down -v

health: health-backend health-website health-backoffice
	@echo "OK: todos los servicios responden"

health-backend:
	@curl -fsS http://localhost:8000/docs > /dev/null
	@echo "OK backend: http://localhost:8000/docs"

health-website:
	@curl -fsS http://localhost:3000 > /dev/null
	@echo "OK website: http://localhost:3000"

health-backoffice:
	@curl -fsS http://localhost:3001 > /dev/null
	@echo "OK backoffice: http://localhost:3001"
