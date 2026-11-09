# Analisis de endpoints FastAPI: coste y frecuencia

Fecha: 2026-08-10
Fuente principal: backend en services/incidents-api + consumo actual del backoffice.

Nota de metodologia:
- La frecuencia de llamada es una estimacion cualitativa (alta/media/baja/muy baja) basada en el codigo cliente actual.
- El coste es relativo (bajo/medio/alto/muy alto) segun numero de lecturas/escrituras, scans, agregaciones y CPU.
- La frecuencia de cambio de datos subyacentes indica cuanto cambian las tablas/colecciones que consulta cada endpoint.

## 1) Inventario (/inventory)

| Endpoint | Coste de operacion | Frecuencia de llamada | Frecuencia de cambio de datos subyacentes | Razon tecnica |
|---|---|---|---|---|
| GET /inventory/products | Alto | Alta | Alta | Lista SKUs y para cada SKU calcula stock con 2 agregaciones (entradas/salidas), patron tipo N+1 de consultas. |
| POST /inventory/products | Medio | Baja | Media | Verifica duplicado + inserta SKU + devuelve con stock calculado. |
| GET /inventory/products/{id} | Medio | Baja | Alta | Lee SKU por id y calcula stock agregado del SKU. |
| POST /inventory/orders/inbound | Medio | Media | Alta | Lee SKU, valida warehouse e inserta StockEntry. |
| POST /inventory/orders/outbound | Medio-Alto | Media | Alta | Lee SKU + calcula stock actual agregado + valida no negativo + inserta StockExit. |
| GET /inventory/orders | Alto | Media | Alta | Carga todas entradas y salidas, unifica en memoria y ordena por fecha. |

## 2) Proveedores (/suppliers)

| Endpoint | Coste de operacion | Frecuencia de llamada | Frecuencia de cambio de datos subyacentes | Razon tecnica |
|---|---|---|---|---|
| POST /suppliers | Medio | Baja | Media | Inserta proveedor tras revisar duplicados por nombre+pais recorriendo proveedores. |
| GET /suppliers | Medio-Alto | Alta | Media | Lee todos los proveedores y filtra en Python por pais/categoria. |
| GET /suppliers/{supplier_id} | Bajo | Muy baja | Media | Lectura puntual por doc_id. |
| PATCH /suppliers/{supplier_id}/rate | Bajo | Media | Media | Actualiza tarifa y timestamp por doc_id. |
| PATCH /suppliers/{supplier_id}/status | Bajo | Media | Media | Actualiza estado por doc_id. |
| DELETE /suppliers/{supplier_id} | Bajo | Muy baja | Media | Borra registro por doc_id. |

## 3) Incidencias operativas (/api/incidents)

| Endpoint | Coste de operacion | Frecuencia de llamada | Frecuencia de cambio de datos subyacentes | Razon tecnica |
|---|---|---|---|---|
| POST /api/incidents | Bajo-Medio | Media | Alta | Inserta incidente en TinyDB. |
| GET /api/incidents | Medio-Alto | Alta | Alta | Lee toda la tabla y filtra en memoria por estado/origen/sede/categoria. |
| GET /api/incidents/summary | Medio-Alto | Alta | Alta | Lee todos los incidentes y agrega contadores por estado/categoria/origen/sede. |
| GET /api/incidents/{incident_id} | Bajo | Muy baja | Alta | Lectura puntual por id. |
| PATCH /api/incidents/{incident_id}/status | Bajo-Medio | Media | Alta | Lee incidente, valida transicion de estado y actualiza estado+updated_at. |
| POST /api/incidents/analyze | Muy alto | Baja | N/A (depende del CSV subido) | Lee archivo completo, valida filas y genera resumen agregado; coste O(n filas). |
| GET /api/incidents/results/export | Bajo | Baja | Baja | Serializa a CSV el ultimo resumen guardado en memoria. |

## 4) Usuarios, perfiles y autenticacion

| Endpoint | Coste de operacion | Frecuencia de llamada | Frecuencia de cambio de datos subyacentes | Razon tecnica |
|---|---|---|---|---|
| POST /users | Medio | Baja | Baja-Media | Alta de usuario: valida email unico por scan, hashea password, crea perfil. |
| GET /users | Medio-Alto | Muy baja | Baja-Media | Lista todos los usuarios y construye perfil asociado por usuario. |
| GET /users/by-email | Medio | Muy baja | Baja-Media | Busca por email con scan y adjunta perfil. |
| GET /users/{user_id} | Medio | Muy baja | Baja-Media | Lee usuario por id + busca perfil del usuario. |
| PUT /users/{user_id} | Medio | Muy baja | Baja-Media | Valida permisos, posible hash de password, posible validacion de email unico. |
| DELETE /users/{user_id} | Medio | Muy baja | Baja-Media | Elimina usuario y su perfil asociado. |
| GET /profiles/me | Medio | Muy baja | Baja | Lee usuario actual y perfil asociado. |
| PUT /profiles/me | Bajo-Medio | Baja | Baja | Actualiza campos de perfil del usuario autenticado. |
| POST /auth/login | Medio | Media | Baja | Busca usuario por email, verifica hash, emite JWT. |
| GET /auth/me | Medio | Alta | Baja | Se llama al iniciar app/refresh; decodifica token y carga usuario+perfil. |
| POST /auth/forgot-password | Medio | Baja | Baja | Busca usuario, genera token reset, persiste token y envia email. |
| POST /auth/reset-password | Medio-Alto | Baja | Baja | Valida token JWT, busca jti, marca token usado y actualiza password. |
| POST /auth/change-password | Medio | Baja | Baja | Verifica password actual y actualiza hash. |

## 5) Priorizacion de optimizacion (impacto)

1. GET /inventory/products
2. GET /inventory/orders
3. GET /api/incidents y GET /api/incidents/summary
4. GET /suppliers
5. GET /auth/me (por frecuencia alta, aunque coste medio)

## 6) Recomendaciones inmediatas

1. Evitar scans completos en listados con filtros: llevar filtros a consulta (o migrar de TinyDB a SQL para esos dominios).
2. Reducir patron N+1 en inventario: preagregar stock por sku+warehouse en una sola consulta.
3. Cache corto para endpoints de lectura pesada si el negocio lo permite (ej. 15-60s en paneles).
4. Introducir telemetria de latencia p95/p99 por endpoint para pasar de estimaciones a datos reales.
