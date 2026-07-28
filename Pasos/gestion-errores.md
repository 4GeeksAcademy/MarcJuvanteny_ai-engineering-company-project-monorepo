# Gestión de Errores — Especificación

Especificación funcional para endurecer el manejo de errores en el frontend (Next.js / TypeScript), el backend (Python / FastAPI), los scripts (Python) y el código base en general de TrackFlow.

## Frontend (Next.js / TypeScript)

- [x] Identifica todas las llamadas `fetch` o a una API en el frontend y verifica que cada una tenga un bloque `try/catch` específico para esa llamada.
- [x] Para cada operación asíncrona que cargue datos, implementa el patrón de UI de tres estados: cargando (spinner o skeleton), éxito (datos visibles), error (mensaje con llamada a la acción).
- [x] Reemplaza cualquier mensaje de error en crudo (`Error 500`, `Unexpected token`, etc.) por una explicación legible para el usuario.
- [x] Asegúrate de que todo estado de error incluya una llamada a la acción clara: un botón de reintentar, un enlace a la página principal o un prompt para contactar soporte.
- [x] Usa `optional chaining` (`?.`) al acceder a propiedades anidadas que podrían ser `undefined`.
- [x] Añade `defaults` o `fallbacks` seguros para valores que podrían ser `null` o `undefined` al renderizar.
- [x] Usa bloques `finally` para asegurar que los estados de carga siempre se limpien, independientemente del resultado.

## Backend (Python / FastAPI)

- [x] Revisa cada handler de ruta y asegúrate de que las excepciones se capturen en el ámbito correcto — evita bloques `try/except` grandes que engullen todos los errores.
- [x] Devuelve respuestas HTTP de error apropiadas (`400`, `404`, `422`, `500`) con un cuerpo JSON limpio y estructurado — sin tracebacks de Python en crudo.
- [x] Asegúrate de que las respuestas de error no exponen datos sensibles (cadenas de conexión a base de datos, rutas internas, claves secretas).
- [x] Añade gestión de errores a todas las llamadas a APIs externas que se hagan desde el backend (por ejemplo, llamadas a un LLM o a un servicio de terceros).

## Scripts (Python)

- [x] Envuelve las operaciones de lectura/escritura de archivos y el parseo de CSV en bloques `try/except` con mensajes de error informativos impresos en `stderr`.
- [x] Asegúrate de que los scripts terminan con un código distinto de cero (`sys.exit(1)`) cuando ocurre un error crítico.
- [x] Añade comprobaciones defensivas para datos de entrada faltantes o malformados antes de que comience el procesamiento.

## General

- [x] Revisa el código base en busca de `console.error` o sentencias `print` que expongan información interna sensible y elimínalos o reemplázalos.

## Notas de implementación

- `uis/website` no tiene llamadas `fetch`/API en sus componentes (el formulario de cotización es solo validación de cliente), por lo que no requirió cambios.
- `uis/backoffice` era el objetivo principal. Cambios clave:
  - `lib/auth-context.tsx`: `authFetch` y `login` ahora capturan el `fetch` en su propio `try/catch` y lanzan un mensaje de red legible en vez de dejar propagar `TypeError: Failed to fetch`.
  - `register-form.tsx`: mismo tratamiento en su llamada directa a `fetch`.
  - `suppliers-directory-panel.tsx` e `incidents-management-panel.tsx`: parseo seguro de JSON (`.json().catch(() => null)`) antes de leer `data.detail`, reemplazado por el helper `extractErrorMessage`/`getGeneralErrorMessage` para evitar mostrar `SyntaxError: Unexpected token` en pantalla.
  - `suppliers-directory-panel.tsx`: se separó el error de carga del listado (`listError`, con botón "Reintentar") del error de las acciones del formulario (`feedbackError`), siguiendo el patrón ya usado en `incidents-management-panel.tsx`.
  - `incidents-management-panel.tsx`: se añadió botón "Reintentar" al error del panel de métricas y se aplicó `optional chaining` al leer `summary.by_status?.[status]` (y equivalentes) por si el backend no devuelve alguna de las claves.
  - `incident-analysis-panel.tsx`: parseo seguro de JSON antes de leer `data?.detail`.
- `services/incidents-api` (FastAPI) ya seguía en gran parte las buenas prácticas: cada ruta delega en servicios que lanzan `HTTPException` con `detail` limpio, hay un `exception_handler(RequestValidationError)` (400) y un `exception_handler(Exception)` genérico (500 sin traceback), y la única llamada a una API externa (Resend, en `email_service.py`) ya estaba envuelta en `try/except urllib.error.URLError`. Cambio aplicado:
  - `email_service.py`: el `print` de error al fallar el envío del email ahora escribe en `stderr` en vez de `stdout`.
- Scripts (Python) — antes fallaban en silencio o con traceback crudo ante errores de E/S:
  - `scripts/seed_incidents.py`: si el CSV no existe, ahora imprime en `stderr` y termina con `sys.exit(1)` (antes hacía `return` y salía con código 0 sin haber hecho nada). La lectura del CSV y la escritura en TinyDB se envuelven en `try/except OSError/csv.Error` con mensaje informativo en `stderr` y `sys.exit(1)`.
  - `services/incidents-api/seed.py`: la escritura en TinyDB se envuelve en `try/except OSError` con mensaje en `stderr` y `sys.exit(1)`.
  - `analyze.py`: los mensajes de `Error: ...` ahora se imprimen en `stderr` (antes iban a `stdout`); la exportación a `results.csv` se envuelve en `try/except OSError` con mensaje en `stderr`.
  - Verificado manualmente con un venv temporal: CSV inexistente → `stderr` + exit 1; fallo de permiso de escritura en la base de datos → `stderr` + exit 1; caso feliz → exit 0.
- General: no se encontraron `console.error`/`console.log`/`console.warn` en `uis/backoffice` ni `uis/website`, y no había `print` en el backend/scripts que expusiera secretos (claves, cadenas de conexión) — solo el caso ya documentado en `.env.example` de mostrar el enlace de restablecimiento en consola cuando `RESEND_API_KEY` no está configurada, que es un fallback intencional para desarrollo local.
