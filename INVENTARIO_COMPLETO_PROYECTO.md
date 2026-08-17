# Inventario completo del proyecto (organizado por carpetas)

Este documento muestra todas las carpetas y archivos del repositorio (excluyendo .git), agrupados por ubicación para facilitar dónde está cada documento.

## Resumen

- Total de carpetas: 71
- Total de archivos: 190

## Índice de carpetas de primer nivel

- .agents
- .vscode
- agents
- data
- docs
- infra
- internal
- mcps
- memory-bank
- packages
- Pasos
- scripts
- services
- shared
- skills
- uis
- workflows

## Raíz del repositorio (.)

- Propósito: Raíz del monorepo; contiene módulos, documentación y configuración global.
- Subcarpetas:
  - .agents — Carpeta auxiliar con notas internas de agentes para control y verificación.
  - .vscode — Configuración local del editor para este workspace.
  - agents — Plantillas y documentación para construir agentes del proyecto.
  - data — Área de datos organizada por etapa del pipeline analítico.
  - docs — Documentación técnica y de arquitectura del monorepo.
  - infra — Espacio para infraestructura, despliegues y operaciones.
  - internal — Material interno no orientado a entrega externa.
  - mcps — Componentes o definición de servidores/protocolos MCP.
  - memory-bank — Memoria de proyecto: brief, contexto técnico y progreso.
  - packages — Paquetes compartidos y recursos reutilizables entre apps.
  - Pasos — Documentación paso a paso de implementación por historias o tareas.
  - scripts — Scripts operativos y automatizaciones auxiliares.
  - services — Backend y servicios de negocio.
  - shared — Documentación/carpeta reservada para recursos compartidos transversales.
  - skills — Biblioteca de skills/prompts y recursos de soporte para agentes.
  - uis — Aplicaciones de interfaz (backoffice y website).
  - workflows — Documentación de flujos operativos y de trabajo.
- Archivos:
  - .gitignore — Define archivos y carpetas que Git no debe versionar.
  - AGENTS.md — Reglas operativas obligatorias para agentes que trabajan en este monorepo.
  - analyze.py — Script de análisis de incidencias y generación de resultados.
  - CACHING_REPORT.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - CONTEXT-trackflow.md — Contexto específico del caso de negocio TrackFlow.
  - CONTEXT.es.md — Contexto funcional/técnico general del proyecto en español.
  - CONTEXT.md — Contexto funcional/técnico general del proyecto en inglés.
  - docker-compose.yml — Orquestación local de servicios con Docker Compose.
  - event-shcemas.json — Esquemas y reglas de validación para eventos de telemetría.
  - incident_analysis.py — Lógica de análisis adicional de incidencias para reporting técnico.
  - INVENTARIO_COMPLETO_PROYECTO.md — Inventario completo de carpetas y archivos del repositorio con propósito por ruta.
  - Makefile — Atajos de comandos de desarrollo, calidad y automatización.
  - package-lock.json — Lockfile de dependencias npm para instalaciones reproducibles.
  - README.es.md — Documentación principal del proyecto en español.
  - README.md — Documentación principal del proyecto en inglés.
  - results.csv — Salida tabular con resultados de análisis o procesamiento.
  - telemetry-plan.md — Plan funcional y técnico de telemetría (eventos, métricas, decisiones).

## Carpeta: .agents

- Propósito: Carpeta auxiliar con notas internas de agentes para control y verificación.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - .agents/Verificaciondecontratos.md — Guía interna para verificación de contratos o acuerdos técnicos.

## Carpeta: .vscode

- Propósito: Configuración local del editor para este workspace.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - .vscode/settings.json — Configuración del workspace en VS Code para estandarizar la experiencia de desarrollo.

## Carpeta: agents

- Propósito: Plantillas y documentación para construir agentes del proyecto.
- Carpeta padre: .
- Subcarpetas (2):
  - agents/_template — Base reutilizable para crear nuevos agentes.
  - agents/tools — Documentación de herramientas y utilidades usadas por agentes.
- Archivos (2):
  - agents/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - agents/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: agents/_template

- Propósito: Base reutilizable para crear nuevos agentes.
- Carpeta padre: agents
- Subcarpetas (1):
  - agents/_template/tests — Plantillas de pruebas para nuevos agentes.
- Archivos (3):
  - agents/_template/agent.py — Script o módulo Python con lógica de negocio, datos o automatización.
  - agents/_template/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - agents/_template/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: agents/_template/tests

- Propósito: Plantillas de pruebas para nuevos agentes.
- Carpeta padre: agents/_template
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - agents/_template/tests/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - agents/_template/tests/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: agents/tools

- Propósito: Documentación de herramientas y utilidades usadas por agentes.
- Carpeta padre: agents
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - agents/tools/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - agents/tools/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: data

- Propósito: Área de datos organizada por etapa del pipeline analítico.
- Carpeta padre: .
- Subcarpetas (4):
  - data/eval — Datos y recursos de evaluación/calidad.
  - data/pipelines — Definiciones y documentación de pipelines de datos.
  - data/process — Datos en procesamiento intermedio.
  - data/raw — Datos en bruto de entrada.
- Archivos (0):
  - (ninguno)

## Carpeta: data/eval

- Propósito: Datos y recursos de evaluación/calidad.
- Carpeta padre: data
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - data/eval/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - data/eval/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: data/pipelines

- Propósito: Definiciones y documentación de pipelines de datos.
- Carpeta padre: data
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - data/pipelines/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - data/pipelines/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: data/process

- Propósito: Datos en procesamiento intermedio.
- Carpeta padre: data
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - data/process/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - data/process/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: data/raw

- Propósito: Datos en bruto de entrada.
- Carpeta padre: data
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - data/raw/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - data/raw/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: docs

- Propósito: Documentación técnica y de arquitectura del monorepo.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (3):
  - docs/ARQUITECTURE_PROPOSAL.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - docs/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - docs/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: infra

- Propósito: Espacio para infraestructura, despliegues y operaciones.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - infra/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - infra/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: internal

- Propósito: Material interno no orientado a entrega externa.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - internal/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - internal/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: mcps

- Propósito: Componentes o definición de servidores/protocolos MCP.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - mcps/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - mcps/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: memory-bank

- Propósito: Memoria de proyecto: brief, contexto técnico y progreso.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (3):
  - memory-bank/progress.md — Estado de avance por hitos y funcionalidades.
  - memory-bank/projectbrief.md — Resumen de negocio, alcance y objetivo del proyecto.
  - memory-bank/techContext.md — Stack, decisiones de arquitectura y restricciones técnicas.

## Carpeta: packages

- Propósito: Paquetes compartidos y recursos reutilizables entre apps.
- Carpeta padre: .
- Subcarpetas (1):
  - packages/shared — Código y tipos compartidos para distintos hitos/apps.
- Archivos (2):
  - packages/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - packages/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: packages/shared

- Propósito: Código y tipos compartidos para distintos hitos/apps.
- Carpeta padre: packages
- Subcarpetas (2):
  - packages/shared/hito2 — Módulo compartido del hito 2 con datos, transformaciones y ejecuciones.
  - packages/shared/types — Exportaciones generales de tipos compartidos.
- Archivos (1):
  - packages/shared/package.json — Archivo JSON de configuración o datos estructurados.

## Carpeta: packages/shared/hito2

- Propósito: Módulo compartido del hito 2 con datos, transformaciones y ejecuciones.
- Carpeta padre: packages/shared
- Subcarpetas (2):
  - packages/shared/hito2/types — Tipos del dominio para hito 2.
  - packages/shared/hito2/utils — Utilidades de colección, validación y transformación.
- Archivos (3):
  - packages/shared/hito2/demo-data.ts — Archivo TypeScript con lógica de aplicación o configuración.
  - packages/shared/hito2/index.ts — Archivo TypeScript con lógica de aplicación o configuración.
  - packages/shared/hito2/run-dashboard.ts — Archivo TypeScript con lógica de aplicación o configuración.

## Carpeta: packages/shared/hito2/types

- Propósito: Tipos del dominio para hito 2.
- Carpeta padre: packages/shared/hito2
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - packages/shared/hito2/types/models.ts — Definición de tipos TypeScript para contratos de datos.

## Carpeta: packages/shared/hito2/utils

- Propósito: Utilidades de colección, validación y transformación.
- Carpeta padre: packages/shared/hito2
- Subcarpetas (0):
  - (ninguna)
- Archivos (3):
  - packages/shared/hito2/utils/collections.ts — Utilidad o capa de acceso a datos/negocio reutilizable.
  - packages/shared/hito2/utils/transformations.ts — Utilidad o capa de acceso a datos/negocio reutilizable.
  - packages/shared/hito2/utils/validations.ts — Utilidad o capa de acceso a datos/negocio reutilizable.

## Carpeta: packages/shared/types

- Propósito: Exportaciones generales de tipos compartidos.
- Carpeta padre: packages/shared
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - packages/shared/types/index.ts — Definición de tipos TypeScript para contratos de datos.

## Carpeta: Pasos

- Propósito: Documentación paso a paso de implementación por historias o tareas.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (14):
  - Pasos/analisis-endpoints-fastapi-coste-frecuencia.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/candidatos-caching-endpoints.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/docker-compose-fullstack.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/gestion-errores.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/gestion-incidencias.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/implementacion-caching-endpoints.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/integracion-api-inventario.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/inventario-productos-ordenes.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/inventario-salida-historial.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/lazy-loading-candidatos-nextjs.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/proteccion-rutas-inventario.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/recuperacion-contrasena.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/registro-ordenes.md — Documento Markdown de soporte funcional, técnico o de proceso.
  - Pasos/usememo-oportunidad-incidents-panel.md — Documento Markdown de soporte funcional, técnico o de proceso.

## Carpeta: scripts

- Propósito: Scripts operativos y automatizaciones auxiliares.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (3):
  - scripts/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - scripts/README.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - scripts/seed_incidents.py — Script o módulo Python con lógica de negocio, datos o automatización.

## Carpeta: services

- Propósito: Backend y servicios de negocio.
- Carpeta padre: .
- Subcarpetas (1):
  - services/incidents-api — Servicio FastAPI para incidencias, inventario y autenticación.
- Archivos (4):
  - services/.dockerignore — Exclusiones al construir imágenes Docker de servicios.
  - services/Dockerfile — Imagen Docker para el entorno de servicios/backend.
  - services/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - services/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: services/incidents-api

- Propósito: Servicio FastAPI para incidencias, inventario y autenticación.
- Carpeta padre: services
- Subcarpetas (1):
  - services/incidents-api/routers — Módulos de rutas de la API.
- Archivos (16):
  - services/incidents-api/.env — Variables de entorno locales (no apto para compartir públicamente).
  - services/incidents-api/.env.example — Plantilla de variables de entorno requeridas.
  - services/incidents-api/auth_service.py — Servicios de autenticación y validación de credenciales.
  - services/incidents-api/database.py — Conexión y utilidades de acceso a base de datos.
  - services/incidents-api/email_service.py — Envío y plantillas de correo para flujos de usuario.
  - services/incidents-api/main.py — Punto de entrada de la API FastAPI de incidencias e inventario.
  - services/incidents-api/models.py — Modelos de dominio y persistencia de la API.
  - services/incidents-api/password_reset_service.py — Lógica de recuperación y reseteo de contraseña.
  - services/incidents-api/pyproject.toml — Configuración del proyecto Python y herramientas.
  - services/incidents-api/README.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - services/incidents-api/requirements.txt — Dependencias Python para instalación tradicional con pip.
  - services/incidents-api/schemas.py — Schemas de validación/serialización para requests y responses.
  - services/incidents-api/seed.py — Inicialización de datos de prueba o bootstrap de la API.
  - services/incidents-api/suppliers.json — Dataset semilla de proveedores para pruebas o carga inicial.
  - services/incidents-api/user_service.py — Operaciones de negocio relacionadas con usuarios.
  - services/incidents-api/uv.lock — Lockfile de dependencias Python gestionadas con uv.

## Carpeta: services/incidents-api/routers

- Propósito: Módulos de rutas de la API.
- Carpeta padre: services/incidents-api
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - services/incidents-api/routers/__init__.py — Inicialización del paquete de routers.
  - services/incidents-api/routers/inventory.py — Rutas HTTP del dominio de inventario.

## Carpeta: shared

- Propósito: Documentación/carpeta reservada para recursos compartidos transversales.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - shared/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - shared/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: skills

- Propósito: Biblioteca de skills/prompts y recursos de soporte para agentes.
- Carpeta padre: .
- Subcarpetas (4):
  - skills/_template — Plantilla base para crear nuevas skills.
  - skills/code-review — Espacio de skill orientada a revisión de código.
  - skills/data-analysis — Skill orientada a análisis de datos y métricas.
  - skills/research — Skill orientada a investigación y descubrimiento.
- Archivos (2):
  - skills/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - skills/README.md — Documento README con guía de uso, estructura y decisiones del módulo.

## Carpeta: skills/_template

- Propósito: Plantilla base para crear nuevas skills.
- Carpeta padre: skills
- Subcarpetas (3):
  - skills/_template/examples — Ejemplos de uso para plantilla de skills.
  - skills/_template/resources — Recursos auxiliares para plantilla de skills.
  - skills/_template/scripts — Scripts auxiliares para plantilla de skills.
- Archivos (1):
  - skills/_template/SKILL.md — Documento Markdown de soporte funcional, técnico o de proceso.

## Carpeta: skills/_template/examples

- Propósito: Ejemplos de uso para plantilla de skills.
- Carpeta padre: skills/_template
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - skills/_template/examples/.gitkeep — Archivo marcador para mantener carpetas vacías en Git.

## Carpeta: skills/_template/resources

- Propósito: Recursos auxiliares para plantilla de skills.
- Carpeta padre: skills/_template
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - skills/_template/resources/.gitkeep — Archivo marcador para mantener carpetas vacías en Git.

## Carpeta: skills/_template/scripts

- Propósito: Scripts auxiliares para plantilla de skills.
- Carpeta padre: skills/_template
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - skills/_template/scripts/.gitkeep — Archivo marcador para mantener carpetas vacías en Git.

## Carpeta: skills/code-review

- Propósito: Espacio de skill orientada a revisión de código.
- Carpeta padre: skills
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - skills/code-review/.gitkeep — Archivo marcador para mantener carpetas vacías en Git.

## Carpeta: skills/data-analysis

- Propósito: Skill orientada a análisis de datos y métricas.
- Carpeta padre: skills
- Subcarpetas (2):
  - skills/data-analysis/resources — Recursos de apoyo para análisis de datos.
  - skills/data-analysis/scripts — Scripts del skill de análisis de datos.
- Archivos (0):
  - (ninguno)

## Carpeta: skills/data-analysis/resources

- Propósito: Recursos de apoyo para análisis de datos.
- Carpeta padre: skills/data-analysis
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - skills/data-analysis/resources/common_metrics.md — Documento Markdown de soporte funcional, técnico o de proceso.

## Carpeta: skills/data-analysis/scripts

- Propósito: Scripts del skill de análisis de datos.
- Carpeta padre: skills/data-analysis
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - skills/data-analysis/scripts/pandas_clean.py — Script o módulo Python con lógica de negocio, datos o automatización.

## Carpeta: skills/research

- Propósito: Skill orientada a investigación y descubrimiento.
- Carpeta padre: skills
- Subcarpetas (2):
  - skills/research/examples — Ejemplos para flujo de investigación.
  - skills/research/templates — Plantillas para resultados de investigación.
- Archivos (0):
  - (ninguno)

## Carpeta: skills/research/examples

- Propósito: Ejemplos para flujo de investigación.
- Carpeta padre: skills/research
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - skills/research/examples/.gitkeep — Archivo marcador para mantener carpetas vacías en Git.

## Carpeta: skills/research/templates

- Propósito: Plantillas para resultados de investigación.
- Carpeta padre: skills/research
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - skills/research/templates/.gitkeep — Archivo marcador para mantener carpetas vacías en Git.

## Carpeta: uis

- Propósito: Aplicaciones de interfaz (backoffice y website).
- Carpeta padre: .
- Subcarpetas (2):
  - uis/backoffice — Aplicación interna de operaciones y gestión logística.
  - uis/website — Sitio web público corporativo.
- Archivos (5):
  - uis/.dockerignore — Exclusiones para build de imágenes Docker de UI.
  - uis/Dockerfile — Imagen Docker para aplicaciones de interfaz de usuario.
  - uis/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - uis/README.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - uis/start.sh — Script de arranque para levantar UIs en entorno local/contenedor.

## Carpeta: uis/backoffice

- Propósito: Aplicación interna de operaciones y gestión logística.
- Carpeta padre: uis
- Subcarpetas (2):
  - uis/backoffice/public — Assets públicos estáticos del backoffice.
  - uis/backoffice/src — Código fuente del backoffice.
- Archivos (9):
  - uis/backoffice/.gitignore — Reglas de exclusión de archivos para Git.
  - uis/backoffice/eslint.config.mjs — Configuración o script JavaScript para toolchain del frontend.
  - uis/backoffice/next.config.ts — Archivo TypeScript con lógica de aplicación o configuración.
  - uis/backoffice/package-lock.json — Archivo JSON de configuración o datos estructurados.
  - uis/backoffice/package.json — Archivo JSON de configuración o datos estructurados.
  - uis/backoffice/postcss.config.mjs — Configuración o script JavaScript para toolchain del frontend.
  - uis/backoffice/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - uis/backoffice/README.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - uis/backoffice/tsconfig.json — Archivo JSON de configuración o datos estructurados.

## Carpeta: uis/backoffice/public

- Propósito: Assets públicos estáticos del backoffice.
- Carpeta padre: uis/backoffice
- Subcarpetas (0):
  - (ninguna)
- Archivos (5):
  - uis/backoffice/public/file.svg — Recurso gráfico estático para la interfaz.
  - uis/backoffice/public/globe.svg — Recurso gráfico estático para la interfaz.
  - uis/backoffice/public/next.svg — Recurso gráfico estático para la interfaz.
  - uis/backoffice/public/vercel.svg — Recurso gráfico estático para la interfaz.
  - uis/backoffice/public/window.svg — Recurso gráfico estático para la interfaz.

## Carpeta: uis/backoffice/src

- Propósito: Código fuente del backoffice.
- Carpeta padre: uis/backoffice
- Subcarpetas (3):
  - uis/backoffice/src/app — Enrutado y páginas de la app Next.js (App Router).
  - uis/backoffice/src/components — Componentes de UI y paneles funcionales del backoffice.
  - uis/backoffice/src/lib — Librerías de acceso a API, auth y utilidades de dominio.
- Archivos (0):
  - (ninguno)

## Carpeta: uis/backoffice/src/app

- Propósito: Enrutado y páginas de la app Next.js (App Router).
- Carpeta padre: uis/backoffice/src
- Subcarpetas (5):
  - uis/backoffice/src/app/(protected) — Rutas protegidas para usuarios autenticados.
  - uis/backoffice/src/app/forgot-password — Carpeta del módulo para organizar recursos de forgot-password.
  - uis/backoffice/src/app/login — Carpeta del módulo para organizar recursos de login.
  - uis/backoffice/src/app/register — Carpeta del módulo para organizar recursos de register.
  - uis/backoffice/src/app/reset-password — Carpeta del módulo para organizar recursos de reset-password.
- Archivos (3):
  - uis/backoffice/src/app/favicon.ico — Recurso gráfico estático para la interfaz.
  - uis/backoffice/src/app/globals.css — Archivo del proyecto con propósito específico del módulo donde reside.
  - uis/backoffice/src/app/layout.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)

- Propósito: Rutas protegidas para usuarios autenticados.
- Carpeta padre: uis/backoffice/src/app
- Subcarpetas (5):
  - uis/backoffice/src/app/(protected)/account — Carpeta del módulo para organizar recursos de account.
  - uis/backoffice/src/app/(protected)/incidents — Carpeta del módulo para organizar recursos de incidents.
  - uis/backoffice/src/app/(protected)/incidents-analysis — Carpeta del módulo para organizar recursos de incidents-analysis.
  - uis/backoffice/src/app/(protected)/inventory — Carpeta del módulo para organizar recursos de inventory.
  - uis/backoffice/src/app/(protected)/suppliers — Carpeta del módulo para organizar recursos de suppliers.
- Archivos (2):
  - uis/backoffice/src/app/(protected)/layout.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.
  - uis/backoffice/src/app/(protected)/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/account

- Propósito: Carpeta del módulo para organizar recursos de account.
- Carpeta padre: uis/backoffice/src/app/(protected)
- Subcarpetas (2):
  - uis/backoffice/src/app/(protected)/account/change-password — Carpeta del módulo para organizar recursos de change-password.
  - uis/backoffice/src/app/(protected)/account/profile — Carpeta del módulo para organizar recursos de profile.
- Archivos (0):
  - (ninguno)

## Carpeta: uis/backoffice/src/app/(protected)/account/change-password

- Propósito: Carpeta del módulo para organizar recursos de change-password.
- Carpeta padre: uis/backoffice/src/app/(protected)/account
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/(protected)/account/change-password/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/account/profile

- Propósito: Carpeta del módulo para organizar recursos de profile.
- Carpeta padre: uis/backoffice/src/app/(protected)/account
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/(protected)/account/profile/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/incidents

- Propósito: Carpeta del módulo para organizar recursos de incidents.
- Carpeta padre: uis/backoffice/src/app/(protected)
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/(protected)/incidents/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/incidents-analysis

- Propósito: Carpeta del módulo para organizar recursos de incidents-analysis.
- Carpeta padre: uis/backoffice/src/app/(protected)
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/(protected)/incidents-analysis/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/inventory

- Propósito: Carpeta del módulo para organizar recursos de inventory.
- Carpeta padre: uis/backoffice/src/app/(protected)
- Subcarpetas (2):
  - uis/backoffice/src/app/(protected)/inventory/orders — Carpeta del módulo para organizar recursos de orders.
  - uis/backoffice/src/app/(protected)/inventory/products — Carpeta del módulo para organizar recursos de products.
- Archivos (0):
  - (ninguno)

## Carpeta: uis/backoffice/src/app/(protected)/inventory/orders

- Propósito: Carpeta del módulo para organizar recursos de orders.
- Carpeta padre: uis/backoffice/src/app/(protected)/inventory
- Subcarpetas (2):
  - uis/backoffice/src/app/(protected)/inventory/orders/inbound — Carpeta del módulo para organizar recursos de inbound.
  - uis/backoffice/src/app/(protected)/inventory/orders/outbound — Carpeta del módulo para organizar recursos de outbound.
- Archivos (1):
  - uis/backoffice/src/app/(protected)/inventory/orders/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/inventory/orders/inbound

- Propósito: Carpeta del módulo para organizar recursos de inbound.
- Carpeta padre: uis/backoffice/src/app/(protected)/inventory/orders
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/(protected)/inventory/orders/inbound/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/inventory/orders/outbound

- Propósito: Carpeta del módulo para organizar recursos de outbound.
- Carpeta padre: uis/backoffice/src/app/(protected)/inventory/orders
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/(protected)/inventory/orders/outbound/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/inventory/products

- Propósito: Carpeta del módulo para organizar recursos de products.
- Carpeta padre: uis/backoffice/src/app/(protected)/inventory
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/(protected)/inventory/products/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/(protected)/suppliers

- Propósito: Carpeta del módulo para organizar recursos de suppliers.
- Carpeta padre: uis/backoffice/src/app/(protected)
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/(protected)/suppliers/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/forgot-password

- Propósito: Carpeta del módulo para organizar recursos de forgot-password.
- Carpeta padre: uis/backoffice/src/app
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/forgot-password/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/login

- Propósito: Carpeta del módulo para organizar recursos de login.
- Carpeta padre: uis/backoffice/src/app
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/login/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/register

- Propósito: Carpeta del módulo para organizar recursos de register.
- Carpeta padre: uis/backoffice/src/app
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/register/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/app/reset-password

- Propósito: Carpeta del módulo para organizar recursos de reset-password.
- Carpeta padre: uis/backoffice/src/app
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/backoffice/src/app/reset-password/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/backoffice/src/components

- Propósito: Componentes de UI y paneles funcionales del backoffice.
- Carpeta padre: uis/backoffice/src
- Subcarpetas (0):
  - (ninguna)
- Archivos (15):
  - uis/backoffice/src/components/account-profile-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/auth-guard.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/backoffice-shell.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/change-password-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/forgot-password-form.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/incident-analysis-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/incidents-management-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/inventory-inbound-order-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/inventory-orders-history-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/inventory-outbound-order-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/inventory-products-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/login-form.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/register-form.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/reset-password-form.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/backoffice/src/components/suppliers-directory-panel.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.

## Carpeta: uis/backoffice/src/lib

- Propósito: Librerías de acceso a API, auth y utilidades de dominio.
- Carpeta padre: uis/backoffice/src
- Subcarpetas (1):
  - uis/backoffice/src/lib/hito2 — Espacio reservado para integración de utilidades del hito 2.
- Archivos (4):
  - uis/backoffice/src/lib/api-errors.ts — Utilidad o capa de acceso a datos/negocio reutilizable.
  - uis/backoffice/src/lib/auth-context.tsx — Utilidad o capa de acceso a datos/negocio reutilizable.
  - uis/backoffice/src/lib/auth.ts — Utilidad o capa de acceso a datos/negocio reutilizable.
  - uis/backoffice/src/lib/inventory.ts — Utilidad o capa de acceso a datos/negocio reutilizable.

## Carpeta: uis/backoffice/src/lib/hito2

- Propósito: Espacio reservado para integración de utilidades del hito 2.
- Carpeta padre: uis/backoffice/src/lib
- Subcarpetas (0):
  - (ninguna)
- Archivos (0):
  - (ninguno)

## Carpeta: uis/website

- Propósito: Sitio web público corporativo.
- Carpeta padre: uis
- Subcarpetas (2):
  - uis/website/public — Assets públicos estáticos del website.
  - uis/website/src — Código fuente del website.
- Archivos (9):
  - uis/website/.gitignore — Reglas de exclusión de archivos para Git.
  - uis/website/eslint.config.mjs — Configuración o script JavaScript para toolchain del frontend.
  - uis/website/next.config.ts — Archivo TypeScript con lógica de aplicación o configuración.
  - uis/website/package-lock.json — Archivo JSON de configuración o datos estructurados.
  - uis/website/package.json — Archivo JSON de configuración o datos estructurados.
  - uis/website/postcss.config.mjs — Configuración o script JavaScript para toolchain del frontend.
  - uis/website/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - uis/website/README.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - uis/website/tsconfig.json — Archivo JSON de configuración o datos estructurados.

## Carpeta: uis/website/public

- Propósito: Assets públicos estáticos del website.
- Carpeta padre: uis/website
- Subcarpetas (0):
  - (ninguna)
- Archivos (5):
  - uis/website/public/file.svg — Recurso gráfico estático para la interfaz.
  - uis/website/public/globe.svg — Recurso gráfico estático para la interfaz.
  - uis/website/public/next.svg — Recurso gráfico estático para la interfaz.
  - uis/website/public/vercel.svg — Recurso gráfico estático para la interfaz.
  - uis/website/public/window.svg — Recurso gráfico estático para la interfaz.

## Carpeta: uis/website/src

- Propósito: Código fuente del website.
- Carpeta padre: uis/website
- Subcarpetas (2):
  - uis/website/src/app — Páginas y layouts del website con App Router.
  - uis/website/src/components — Componentes UI específicos del sitio público.
- Archivos (0):
  - (ninguno)

## Carpeta: uis/website/src/app

- Propósito: Páginas y layouts del website con App Router.
- Carpeta padre: uis/website/src
- Subcarpetas (1):
  - uis/website/src/app/application — Ruta del formulario/aplicación comercial.
- Archivos (4):
  - uis/website/src/app/favicon.ico — Recurso gráfico estático para la interfaz.
  - uis/website/src/app/globals.css — Archivo del proyecto con propósito específico del módulo donde reside.
  - uis/website/src/app/layout.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.
  - uis/website/src/app/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/website/src/app/application

- Propósito: Ruta del formulario/aplicación comercial.
- Carpeta padre: uis/website/src/app
- Subcarpetas (0):
  - (ninguna)
- Archivos (1):
  - uis/website/src/app/application/page.tsx — Archivo de página/layout/ruta de Next.js para la interfaz de usuario.

## Carpeta: uis/website/src/components

- Propósito: Componentes UI específicos del sitio público.
- Carpeta padre: uis/website/src
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - uis/website/src/components/landing-interactions.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.
  - uis/website/src/components/quote-form.tsx — Componente React reutilizable para presentar o gestionar funcionalidades de UI.

## Carpeta: workflows

- Propósito: Documentación de flujos operativos y de trabajo.
- Carpeta padre: .
- Subcarpetas (0):
  - (ninguna)
- Archivos (2):
  - workflows/README.es.md — Documento README con guía de uso, estructura y decisiones del módulo.
  - workflows/README.md — Documento README con guía de uso, estructura y decisiones del módulo.
