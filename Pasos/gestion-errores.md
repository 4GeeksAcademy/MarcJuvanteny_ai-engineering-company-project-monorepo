# Gestión de Errores — Especificación

Especificación funcional para endurecer el manejo de errores en el frontend (Next.js / TypeScript) de TrackFlow (`uis/backoffice` y `uis/website`).

## Frontend (Next.js / TypeScript)

- [x] Identifica todas las llamadas `fetch` o a una API en el frontend y verifica que cada una tenga un bloque `try/catch` específico para esa llamada.
- [x] Para cada operación asíncrona que cargue datos, implementa el patrón de UI de tres estados: cargando (spinner o skeleton), éxito (datos visibles), error (mensaje con llamada a la acción).
- [x] Reemplaza cualquier mensaje de error en crudo (`Error 500`, `Unexpected token`, etc.) por una explicación legible para el usuario.
- [x] Asegúrate de que todo estado de error incluya una llamada a la acción clara: un botón de reintentar, un enlace a la página principal o un prompt para contactar soporte.
- [x] Usa `optional chaining` (`?.`) al acceder a propiedades anidadas que podrían ser `undefined`.
- [x] Añade `defaults` o `fallbacks` seguros para valores que podrían ser `null` o `undefined` al renderizar.
- [x] Usa bloques `finally` para asegurar que los estados de carga siempre se limpien, independientemente del resultado.

## Notas de implementación

- `uis/website` no tiene llamadas `fetch`/API en sus componentes (el formulario de cotización es solo validación de cliente), por lo que no requirió cambios.
- `uis/backoffice` era el objetivo principal. Cambios clave:
  - `lib/auth-context.tsx`: `authFetch` y `login` ahora capturan el `fetch` en su propio `try/catch` y lanzan un mensaje de red legible en vez de dejar propagar `TypeError: Failed to fetch`.
  - `register-form.tsx`: mismo tratamiento en su llamada directa a `fetch`.
  - `suppliers-directory-panel.tsx` e `incidents-management-panel.tsx`: parseo seguro de JSON (`.json().catch(() => null)`) antes de leer `data.detail`, reemplazado por el helper `extractErrorMessage`/`getGeneralErrorMessage` para evitar mostrar `SyntaxError: Unexpected token` en pantalla.
  - `suppliers-directory-panel.tsx`: se separó el error de carga del listado (`listError`, con botón "Reintentar") del error de las acciones del formulario (`feedbackError`), siguiendo el patrón ya usado en `incidents-management-panel.tsx`.
  - `incidents-management-panel.tsx`: se añadió botón "Reintentar" al error del panel de métricas y se aplicó `optional chaining` al leer `summary.by_status?.[status]` (y equivalentes) por si el backend no devuelve alguna de las claves.
  - `incident-analysis-panel.tsx`: parseo seguro de JSON antes de leer `data?.detail`.
