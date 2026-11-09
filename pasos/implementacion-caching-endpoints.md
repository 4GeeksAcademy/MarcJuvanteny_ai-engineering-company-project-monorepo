# Implementacion de caching para endpoints candidatos

Fecha: 2026-08-10

## Endpoints cubiertos

1. GET /suppliers
2. GET /auth/me

## Estrategia aplicada

- Cache en memoria con TTL usando diccionarios en `main.py`.
- Locks (`RLock`) para acceso concurrente seguro.
- Invalidacion explicita en endpoints de escritura relacionados.

## Parametros

- `GET /suppliers`: TTL 45s.
- `GET /auth/me`: TTL 20s.

## Claves de cache

- Suppliers: `country=<valor>|category=<valor>`.
- Auth me: token bearer.

## Invalidacion implementada

### Suppliers
Se limpia cache completa de suppliers en:
- POST /suppliers
- PATCH /suppliers/{supplier_id}/rate
- PATCH /suppliers/{supplier_id}/status
- DELETE /suppliers/{supplier_id}

### Auth me
Se invalida por usuario (todas sus entradas de token cacheadas) en:
- PUT /profiles/me
- PUT /users/{user_id}
- DELETE /users/{user_id}
- POST /auth/change-password
- POST /auth/reset-password

## Nota de diseno

- Se mantuvo enfoque local (sin Redis) para minimizar complejidad y cumplir el objetivo inmediato.
- El diseño es compatible con evolucion posterior a Redis si se requiere cache distribuida.
