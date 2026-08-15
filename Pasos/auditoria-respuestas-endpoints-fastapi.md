# Auditoría de respuestas de endpoints FastAPI

Fecha: 2026-08-15

## Órdenes del usuario (registro)
- Orden 1: "Todas las ordenes qeu te voy a dar quiero que las apuntes en un documento nuevo en la carpeta Pasos. Para cada endpoint, documenta su comportamiento de respuesta actual: Usa response_model? Devuelve un objeto ORM en crudo, un dict o un equema tipado?"
- Orden 2: "Clasifica cada endpoint en uno de estos tres estados: Ya serializado, Parcialmente serializado, Sin serializar."
- Orden 3: "Crea o actuliza los esquemas Pydantic para cada endpoint clasificado como Sin serializar o Parcialmente serialziado."
- Orden 4: "Asegurate de que cada endpoint tiene un response_model explícito declarado en su decorador de ruta."
- Orden 5: "Para endpoints de listado: define un esquema que devuelva solo los campos que los consumidores neceistan. Evita devolver objetos anidados completos cuando una representacion clana es suficiente."
- Orden 6: "Para endpoints de escritura (POST, PUT PATCH): define un esquema de entrada separado que acepte únicamente los campos que deben poder escribirse. No reutilices el esquema de respuesta como esquema de entrada."
- Orden 7: "Asegurate de que ningún endpoint exponga campos sensibles (por ejemplo, contraseñas, hasheadas, tokens internos, claves foráneas en bruto cuando hay un objeto anidado disponible)."
- Orden 8: "Cuando una relación sea necesaria en la respuesta, decide explícitamente: devolver el objeto anidado completo, devolver solo el ID relacionado o devolver una proyección plana y documenta esa decisión en tu archivo de auditoría."

## Criterio de clasificación
- Esquema tipado: la función devuelve una instancia tipada (por ejemplo, modelos Pydantic/SQLModel no tabla) o una lista de estas, y/o está normalizada con response_model.
- Dict: la función devuelve un diccionario Python (por ejemplo dict[str, Any]).
- ORM en crudo: devuelve directamente una entidad ORM de persistencia (no detectado en los endpoints actuales).
- Response sin esquema: devuelve un objeto Response (CSV, 204 sin cuerpo, etc.) sin response_model.

## Endpoints y comportamiento de respuesta actual

| Método | Ruta | ¿Usa response_model? | Tipo de retorno actual | Observación |
|---|---|---|---|---|
| GET | /inventory/products | Sí (list[SKUResponse]) | Esquema tipado | Devuelve lista de SKUResponse construida por helper. |
| POST | /inventory/products | Sí (SKUResponse) | Esquema tipado | Devuelve SKUResponse. |
| GET | /inventory/products/{id} | Sí (SKUResponse) | Esquema tipado | Devuelve SKUResponse. |
| POST | /inventory/orders/inbound | Sí (StockEntryResponse) | Esquema tipado | Mapea ORM a StockEntryResponse. |
| POST | /inventory/orders/outbound | Sí (StockExitResponse) | Esquema tipado | Mapea ORM a StockExitResponse. |
| GET | /inventory/orders | Sí (list[StockMovementResponse]) | Esquema tipado | Devuelve lista de StockMovementResponse. |
| POST | /suppliers | Sí (SupplierRecord) | Esquema tipado | Convierte Document de TinyDB a SupplierRecord. |
| GET | /suppliers | Sí (list[SupplierRecord]) | Esquema tipado | Devuelve lista de SupplierRecord. |
| GET | /suppliers/{supplier_id} | Sí (SupplierRecord) | Esquema tipado | Devuelve SupplierRecord. |
| PATCH | /suppliers/{supplier_id}/rate | Sí (SupplierRecord) | Esquema tipado | Devuelve SupplierRecord actualizado. |
| PATCH | /suppliers/{supplier_id}/status | Sí (SupplierRecord) | Esquema tipado | Devuelve SupplierRecord actualizado. |
| DELETE | /suppliers/{supplier_id} | No | Response sin esquema | 204 No Content. |
| POST | /api/incidents | Sí (IncidentRecord) | Esquema tipado | Convierte Document de TinyDB a IncidentRecord. |
| GET | /api/incidents | Sí (list[IncidentRecord]) | Esquema tipado | Devuelve lista de IncidentRecord. |
| GET | /api/incidents/summary | Sí (IncidentSummary) | Esquema tipado | Devuelve IncidentSummary. |
| GET | /api/incidents/{incident_id} | Sí (IncidentRecord) | Esquema tipado | Devuelve IncidentRecord. |
| PATCH | /api/incidents/{incident_id}/status | Sí (IncidentRecord) | Esquema tipado | Devuelve IncidentRecord actualizado. |
| POST | /users | Sí (UserWithProfileRecord) | Esquema tipado | Devuelve UserWithProfileRecord desde servicio. |
| GET | /users | Sí (list[UserWithProfileRecord]) | Esquema tipado | Devuelve lista tipada desde servicio. |
| GET | /users/by-email | Sí (UserWithProfileRecord) | Esquema tipado | Devuelve UserWithProfileRecord. |
| GET | /users/{user_id} | Sí (UserWithProfileRecord) | Esquema tipado | Devuelve UserWithProfileRecord. |
| PUT | /users/{user_id} | Sí (UserWithProfileRecord) | Esquema tipado | Devuelve UserWithProfileRecord actualizado. |
| DELETE | /users/{user_id} | No | Response sin esquema | 204 No Content. |
| GET | /profiles/me | Sí (ProfileRecord) | Esquema tipado | Devuelve ProfileRecord. |
| PUT | /profiles/me | Sí (ProfileRecord) | Esquema tipado | Devuelve ProfileRecord actualizado. |
| POST | /auth/login | Sí (TokenResponse) | Esquema tipado | Devuelve TokenResponse. |
| GET | /auth/me | Sí (AuthMeResponse) | Esquema tipado | Devuelve AuthMeResponse (con cache). |
| POST | /auth/forgot-password | Sí (MessageResponse) | Esquema tipado | Devuelve MessageResponse. |
| POST | /auth/reset-password | Sí (MessageResponse) | Esquema tipado | Devuelve MessageResponse. |
| POST | /auth/change-password | Sí (MessageResponse) | Esquema tipado | Devuelve MessageResponse. |
| POST | /api/incidents/analyze | No | Dict | Devuelve dict[str, Any] con resumen en memoria. |
| GET | /api/incidents/results/export | No | Response sin esquema | Devuelve CSV como text/csv con cabecera Content-Disposition. |

## Resumen rápido
- Total endpoints de negocio revisados: 32.
- Con response_model: 29.
- Sin response_model: 3.
- ORM en crudo detectado: 0.
- Dict detectado: 1 (/api/incidents/analyze).
- Response sin esquema detectado: 2 DELETE 204 + 1 export CSV.

## Clasificación por estado de serialización

### Definiciones aplicadas
- Ya serializado: tiene response_model explícito y el esquema es adecuado para el cliente actual.
- Parcialmente serializado: tiene response_model, pero el esquema expone campos innecesarios o no está alineado con una respuesta pública mínima.
- Sin serializar: devuelve dict sin tipado o respuesta sin contrato de esquema OpenAPI (sin response_model).

### Tabla de clasificación endpoint por endpoint

| Método | Ruta | Estado | Motivo |
|---|---|---|---|
| GET | /inventory/products | Ya serializado | response_model list[SKUResponse], incluye stock calculado y campos de negocio esperados. |
| POST | /inventory/products | Ya serializado | response_model SKUResponse y payload de salida estable. |
| GET | /inventory/products/{id} | Ya serializado | response_model SKUResponse adecuado para consulta individual. |
| POST | /inventory/orders/inbound | Ya serializado | response_model StockEntryResponse con campos del movimiento entrante. |
| POST | /inventory/orders/outbound | Ya serializado | response_model StockExitResponse con validaciones de dominio. |
| GET | /inventory/orders | Ya serializado | response_model list[StockMovementResponse] coherente para timeline de movimientos. |
| POST | /suppliers | Ya serializado | response_model SupplierRecord con contrato tipado completo. |
| GET | /suppliers | Ya serializado | response_model list[SupplierRecord] coherente con filtrado por país/categoría. |
| GET | /suppliers/{supplier_id} | Ya serializado | response_model SupplierRecord adecuado. |
| PATCH | /suppliers/{supplier_id}/rate | Ya serializado | response_model SupplierRecord tras actualización de tarifa. |
| PATCH | /suppliers/{supplier_id}/status | Ya serializado | response_model SupplierRecord tras cambio de estado. |
| DELETE | /suppliers/{supplier_id} | Sin serializar | no define response_model; devuelve Response 204 sin contrato de esquema. |
| POST | /api/incidents | Ya serializado | response_model IncidentRecord tipado. |
| GET | /api/incidents | Ya serializado | response_model list[IncidentRecord] tipado. |
| GET | /api/incidents/summary | Ya serializado | response_model IncidentSummary adecuado para agregados. |
| GET | /api/incidents/{incident_id} | Ya serializado | response_model IncidentRecord tipado. |
| PATCH | /api/incidents/{incident_id}/status | Ya serializado | response_model IncidentRecord tras transición válida. |
| POST | /users | Parcialmente serializado | usa UserWithProfileRecord que hereda hashed_password; expone dato sensible innecesario. |
| GET | /users | Parcialmente serializado | list[UserWithProfileRecord] expone hashed_password para cada usuario. |
| GET | /users/by-email | Parcialmente serializado | UserWithProfileRecord expone hashed_password innecesario para cliente. |
| GET | /users/{user_id} | Parcialmente serializado | UserWithProfileRecord incluye hashed_password. |
| PUT | /users/{user_id} | Parcialmente serializado | UserWithProfileRecord incluye hashed_password tras actualizar usuario. |
| DELETE | /users/{user_id} | Sin serializar | no define response_model; devuelve Response 204 sin contrato de esquema. |
| GET | /profiles/me | Ya serializado | response_model ProfileRecord y campos de perfil adecuados. |
| PUT | /profiles/me | Ya serializado | response_model ProfileRecord tras actualización de perfil. |
| POST | /auth/login | Ya serializado | response_model TokenResponse, sin exponer campos internos de usuario. |
| GET | /auth/me | Ya serializado | response_model AuthMeResponse mínimo y alineado con cliente autenticado. |
| POST | /auth/forgot-password | Ya serializado | response_model MessageResponse simple y estable. |
| POST | /auth/reset-password | Ya serializado | response_model MessageResponse simple y estable. |
| POST | /auth/change-password | Ya serializado | response_model MessageResponse simple y estable. |
| POST | /api/incidents/analyze | Sin serializar | devuelve dict[str, Any] sin response_model explícito. |
| GET | /api/incidents/results/export | Sin serializar | devuelve Response CSV sin response_model/documentación de schema de salida. |

### Resumen de estados
- Ya serializado: 24 endpoints.
- Parcialmente serializado: 5 endpoints.
- Sin serializar: 4 endpoints.
