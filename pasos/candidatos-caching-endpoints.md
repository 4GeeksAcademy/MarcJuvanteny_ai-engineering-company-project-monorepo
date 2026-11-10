# Candidatos de caching (coste + frecuencia + estabilidad)

Fecha: 2026-08-10

## Candidato 1: GET /suppliers

Evaluacion de criterios:
- Coste: Medio-Alto.
- Frecuencia de llamada: Alta (se refresca al entrar al panel y al cambiar filtros).
- Estabilidad de datos: Media (los proveedores no cambian a cada segundo).

Por que encaja:
- Es un endpoint de lectura con filtrado en memoria (scan completo + filtro), por lo que repetirlo frecuentemente cuesta.
- El dato es lo bastante estable para tolerar cache corto sin afectar operacion critica en tiempo real.

Politica sugerida:
- TTL inicial: 30-60 segundos.
- Clave de cache: path + query (`country`, `category`).
- Invalida tras: POST /suppliers, PATCH /suppliers/{id}/rate, PATCH /suppliers/{id}/status, DELETE /suppliers/{id}.

## Candidato 2: GET /auth/me

Evaluacion de criterios:
- Coste: Medio.
- Frecuencia de llamada: Alta (arranque de app, refresh de sesion y recargas de vista).
- Estabilidad de datos: Alta relativa en ventanas cortas (perfil/rol no cambia continuamente).

Por que encaja:
- Se invoca con mucha frecuencia y su respuesta suele repetirse para el mismo token.
- Cache de muy corta vida reduce carga repetida sin riesgo funcional alto.

Politica sugerida:
- TTL inicial: 10-30 segundos.
- Ambito: por token/usuario autenticado.
- Invalida tras: PUT /profiles/me, PUT /users/{id}, POST /auth/change-password, logout/login.

## Nota

No se recomienda empezar por cachear GET /inventory/products o GET /api/incidents/summary si el objetivo es estabilidad alta, porque sus datos subyacentes cambian con mayor frecuencia operativa.
