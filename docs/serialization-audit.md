# Serialization Audit - FastAPI Endpoints

Date: 2026-08-15
Scope: services/incidents-api (`main.py` + `routers/inventory.py`)

## Audit Criteria

- Already serialized: endpoint has an explicit `response_model` and the schema is adequate for client consumption.
- Partially serialized: endpoint has `response_model`, but the schema is incomplete, exposes unnecessary fields, or does not match client needs.
- Not serialized: endpoint returns raw ORM or untyped dict/response without explicit output schema contract.

## Current Behavior Summary

- Total business endpoints audited: 32
- Endpoints with `response_model`: 29
- Endpoints without `response_model`: 3
- Raw ORM returns detected: 0
- Untyped dict returns detected: 1 (`POST /api/incidents/analyze`)
- Response without schema contract: 3 (`DELETE /suppliers/{supplier_id}`, `DELETE /users/{user_id}`, `GET /api/incidents/results/export`)

## Classification by Endpoint

| Method | Route | Status | Notes |
|---|---|---|---|
| GET | /inventory/products | Already serialized | `list[SKUResponse]` with computed stock and stable shape. |
| POST | /inventory/products | Already serialized | `SKUResponse` typed payload. |
| GET | /inventory/products/{id} | Already serialized | `SKUResponse` for single item retrieval. |
| POST | /inventory/orders/inbound | Already serialized | `StockEntryResponse` typed movement output. |
| POST | /inventory/orders/outbound | Already serialized | `StockExitResponse` typed movement output. |
| GET | /inventory/orders | Already serialized | `list[StockMovementResponse]` timeline output. |
| POST | /suppliers | Already serialized | `SupplierRecord` mapped from TinyDB document. |
| GET | /suppliers | Already serialized | `list[SupplierRecord]` typed list output. |
| GET | /suppliers/{supplier_id} | Already serialized | `SupplierRecord` typed output. |
| PATCH | /suppliers/{supplier_id}/rate | Already serialized | `SupplierRecord` typed updated output. |
| PATCH | /suppliers/{supplier_id}/status | Already serialized | `SupplierRecord` typed updated output. |
| DELETE | /suppliers/{supplier_id} | Not serialized | `204 Response` without `response_model`. |
| POST | /api/incidents | Already serialized | `IncidentRecord` typed output. |
| GET | /api/incidents | Already serialized | `list[IncidentRecord]` typed output. |
| GET | /api/incidents/summary | Already serialized | `IncidentSummary` typed aggregated output. |
| GET | /api/incidents/{incident_id} | Already serialized | `IncidentRecord` typed output. |
| PATCH | /api/incidents/{incident_id}/status | Already serialized | `IncidentRecord` typed output after transition. |
| POST | /users | Partially serialized | `UserWithProfileRecord` includes `hashed_password` (unnecessary sensitive field). |
| GET | /users | Partially serialized | `list[UserWithProfileRecord]` exposes `hashed_password` per user. |
| GET | /users/by-email | Partially serialized | `UserWithProfileRecord` exposes `hashed_password`. |
| GET | /users/{user_id} | Partially serialized | `UserWithProfileRecord` exposes `hashed_password`. |
| PUT | /users/{user_id} | Partially serialized | `UserWithProfileRecord` exposes `hashed_password` after update. |
| DELETE | /users/{user_id} | Not serialized | `204 Response` without `response_model`. |
| GET | /profiles/me | Already serialized | `ProfileRecord` typed output. |
| PUT | /profiles/me | Already serialized | `ProfileRecord` typed updated output. |
| POST | /auth/login | Already serialized | `TokenResponse` typed auth token output. |
| GET | /auth/me | Already serialized | `AuthMeResponse` minimal profile for current user. |
| POST | /auth/forgot-password | Already serialized | `MessageResponse` typed output. |
| POST | /auth/reset-password | Already serialized | `MessageResponse` typed output. |
| POST | /auth/change-password | Already serialized | `MessageResponse` typed output. |
| POST | /api/incidents/analyze | Not serialized | Untyped `dict[str, Any]`, no `response_model`. |
| GET | /api/incidents/results/export | Not serialized | CSV `Response` without output schema contract. |

## Status Totals

- Already serialized: 24
- Partially serialized: 5
- Not serialized: 4

## Main Risk Found

User endpoints currently expose `hashed_password` through `UserWithProfileRecord` inheritance. Even if hashed, it is a sensitive field and should not be part of public API response contracts.
