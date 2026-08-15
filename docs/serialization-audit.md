# Serialization Audit - FastAPI Endpoints

Date: 2026-08-15
Scope: services/incidents-api (`main.py` + `routers/inventory.py`)

## Audit Criteria

- Already serialized: endpoint has an explicit `response_model` and the schema is adequate for client consumption.
- Partially serialized: endpoint has `response_model`, but the schema is incomplete, exposes unnecessary fields, or does not match client needs.
- Not serialized: endpoint returns raw ORM or untyped dict/response without explicit output schema contract.

## Current Behavior Summary

- Total business endpoints audited: 32
- Endpoints with `response_model`: 32
- Endpoints without `response_model`: 0
- Raw ORM returns detected: 0
- Untyped dict returns detected: 0
- Response without schema contract: 0

Implementation status: completed for all audited endpoints.

## Classification by Endpoint

| Method | Route | `response_model` | Status | Implemented |
|---|---|---|---|---|
| GET | /inventory/products | `list[SKUResponse]` | Already serialized | ✅ |
| POST | /inventory/products | `SKUResponse` | Already serialized | ✅ |
| GET | /inventory/products/{id} | `SKUResponse` | Already serialized | ✅ |
| POST | /inventory/orders/inbound | `StockEntryResponse` | Already serialized | ✅ |
| POST | /inventory/orders/outbound | `StockExitResponse` | Already serialized | ✅ |
| GET | /inventory/orders | `list[StockMovementResponse]` | Already serialized | ✅ |
| POST | /suppliers | `SupplierRecord` | Already serialized | ✅ |
| GET | /suppliers | `list[SupplierListItem]` | Already serialized | ✅ |
| GET | /suppliers/{supplier_id} | `SupplierRecord` | Already serialized | ✅ |
| PATCH | /suppliers/{supplier_id}/rate | `SupplierRecord` | Already serialized | ✅ |
| PATCH | /suppliers/{supplier_id}/status | `SupplierRecord` | Already serialized | ✅ |
| DELETE | /suppliers/{supplier_id} | `MessageResponse` | Already serialized | ✅ |
| POST | /api/incidents | `IncidentRecord` | Already serialized | ✅ |
| GET | /api/incidents | `list[IncidentListItem]` | Already serialized | ✅ |
| GET | /api/incidents/summary | `IncidentSummary` | Already serialized | ✅ |
| GET | /api/incidents/{incident_id} | `IncidentRecord` | Already serialized | ✅ |
| PATCH | /api/incidents/{incident_id}/status | `IncidentRecord` | Already serialized | ✅ |
| POST | /users | `UserPublicRecord` | Already serialized | ✅ |
| GET | /users | `list[UserListItem]` | Already serialized | ✅ |
| GET | /users/by-email | `UserPublicRecord` | Already serialized | ✅ |
| GET | /users/{user_id} | `UserPublicRecord` | Already serialized | ✅ |
| PUT | /users/{user_id} | `UserPublicRecord` | Already serialized | ✅ |
| DELETE | /users/{user_id} | `MessageResponse` | Already serialized | ✅ |
| GET | /profiles/me | `ProfilePublic` | Already serialized | ✅ |
| PUT | /profiles/me | `ProfilePublic` | Already serialized | ✅ |
| POST | /auth/login | `TokenResponse` | Already serialized | ✅ |
| GET | /auth/me | `AuthMeResponse` | Already serialized | ✅ |
| POST | /auth/forgot-password | `MessageResponse` | Already serialized | ✅ |
| POST | /auth/reset-password | `MessageResponse` | Already serialized | ✅ |
| POST | /auth/change-password | `MessageResponse` | Already serialized | ✅ |
| POST | /api/incidents/analyze | `IncidentAnalysisResponse` | Already serialized | ✅ |
| GET | /api/incidents/results/export | `IncidentAnalysisExportResponse` | Already serialized | ✅ |

## Status Totals

- Already serialized: 32
- Partially serialized: 0
- Not serialized: 0

## Main Risk Found

No critical serialization risk remains open in the audited endpoints.

## Relationship Serialization Decisions (Current Policy)

This section is the current source of truth for relation-shape decisions in API responses.

| Relationship | Endpoints | Decision | Response shape | Rationale |
|---|---|---|---|---|
| User -> Profile (detail) | `POST /users`, `GET /users/by-email`, `GET /users/{user_id}`, `PUT /users/{user_id}` | Return nested object | `profile: ProfilePublic` | Profile context is useful for clients, but internal identifiers are not. |
| User -> Profile (list) | `GET /users` | Return flat projection | `profile_name` only | List views prioritize scanability and payload size over full nested profile data. |
| Profile -> User | `GET /profiles/me`, `PUT /profiles/me` | Do not return raw foreign key | no `user_id` in response | Avoid exposing internal linkage when the identity is already implied by auth context. |
| Stock movement -> SKU | `POST /inventory/orders/inbound`, `POST /inventory/orders/outbound`, `GET /inventory/orders` | Return nested summary object | `sku: SKUSummary` | Business consumers need SKU context; raw `sku_id` is not enough and is internal. |
| Stock entry/exit -> Actor user | same inventory movement endpoints | Do not return internal actor identifier | no `user_uuid` in response | Prevents exposing operational/internal identifiers not required by API consumers. |
| Supplier list/detail | `/suppliers` endpoints | No nested relation needed | scalar fields only | Current contract does not require relational expansion. |
| Incident list/detail | `/api/incidents` endpoints | No nested relation needed | scalar/enums only | Branch/origin/category are already explicit domain values; no extra nested object required. |

### Explicit Strategy Rules

- Use nested objects only when they add direct client value and can be safely sanitized.
- Use flat projections for list endpoints whenever full nested objects are unnecessary.
- Avoid raw foreign keys in output when an equivalent nested summary is available.
- Never expose sensitive fields (`hashed_password`, reset tokens, internal auth artifacts).
