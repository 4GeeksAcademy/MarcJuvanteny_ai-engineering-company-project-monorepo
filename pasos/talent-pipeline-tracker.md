# Talent Pipeline Tracker — Hito 3

Fecha: 2026-11-09

Implementación de `CONTEXT/CONTEXT3.md`. Es el frontend de RRHH que pidió **Ana Whitfield** para seguir el proceso de selección del puesto *Asistente de Dirección, sede Zaragoza*. Desde él se puede:

- ver todos los candidatos;
- filtrarlos por estado y etapa;
- buscarlos por nombre o email sin recargar la página;
- abrir el detalle de cada uno y cambiar su estado y etapa;
- gestionar sus notas;
- dar de alta candidatos y editar sus datos.

Consume la **API mock centralizada del curso**:

- URL base: `https://playground.4geeks.com/tracker/api/v1`
- Documentación: [/docs](https://playground.4geeks.com/tracker/api/v1/docs)

Según el enunciado oficial del hito, va como proyecto independiente en `uis/talent-pipeline-tracker/`.

## Dónde vive el código

```
uis/talent-pipeline-tracker/
  .env.example                       NEXT_PUBLIC_API_URL (.env.local está en el .gitignore del proyecto)
  src/app/page.tsx                   / -> listado (CandidateList dentro de <Suspense>)
  src/app/candidates/[id]/page.tsx   detalle (CandidateDetail dentro de <Suspense>)
  src/types/candidate.ts             contrato de la API: Candidate, CandidateInput, CandidatePatch, Note, CandidatePage
  src/lib/api.ts                     un fetch por endpoint; ApiError con mensajes en español
  src/lib/labels.ts                  status/stage -> etiqueta; formato de fechas es-ES
  src/components/
    candidate-list.tsx               filtros en la URL (useSearchParams), paginación, alta en modal
    candidate-filters.tsx            buscador con debounce + selects de estado y etapa
    candidate-table.tsx              tabla sin notas
    candidate-form.tsx               alta y edición (todos los campos de RecordCreate) con validación
    candidate-detail.tsx             datos, edición, borrado con confirmación
    status-stage-editor.tsx          PATCH de estado y etapa
    notes-panel.tsx                  listar, añadir y borrar notas
    feedback.tsx, badges.tsx, modal.tsx, pagination.tsx
```

## Contrato de la API (comprobado con llamadas reales)

| Método | Ruta | Uso en la app |
|---|---|---|
| GET | `/records?status&stage&search&page&limit` | listado. Responde `{ total, page, limit, data: RecordOut[] }` |
| POST | `/records` | alta (`RecordCreate`, 201) |
| GET / PUT / PATCH / DELETE | `/records/{id}` | detalle, edición, estado/etapa, borrado (204) |
| GET / POST | `/records/{id}/notes` | `{ data: Note[], meta: { total } }` / `{ content }` (201) |
| DELETE | `/records/{id}/notes/{note_id}` | borrar nota (204) |

El OpenAPI no define la forma del listado ni la de las notas. Se obtuvieron de respuestas reales: `Note = { id, record_id, content, created_at }`.

Hay dos formatos de error:

- 404 → `{ "error": "Record not found" }`
- 422 → `{ "detail": [...] }` (FastAPI)

`lib/api.ts` traduce los dos a mensajes en español.

Un detalle: si se filtra por un `status` inválido, la API devuelve 200 con una lista vacía. Por eso la app ignora los valores de la URL que no son válidos y no los envía.

## Criterios de aceptación

| Criterio | Cómo se cumple |
|---|---|
| Nunca se muestran valores crudos de la API | `statusLabel` / `stageLabel` en todos los badges y selects. Un valor desconocido se muestra como "Estado desconocido". |
| Las notas solo se ven en el detalle | La tabla no las usa. El detalle las pide con `GET /records/{id}/notes`. |
| El formulario incluye todos los campos requeridos por la API | `full_name`, `email`, `phone`, `position` y `experience_years` son obligatorios y se validan en el cliente. `linkedin_url` y `cv_url` son opcionales y se envían como `null` si están vacíos. |
| Búsqueda sin recargar | Debounce de 300 ms → `router.replace` → `useEffect` con `AbortController`. |
| Filtros en la URL con `useSearchParams` | `?status=&stage=&search=&page=`. Cualquier cambio de filtro vuelve a la página 1. |
| Carga, éxito y error en cada operación | Listado, detalle, notas, alta, edición, PATCH y borrado. Los errores de carga tienen "Reintentar". |
| Solo hooks de React | `useState`, `useEffect` y `useCallback`; sin Redux ni Zustand. |

## Problemas encontrados

1. **La `key` del editor de estado borraba el mensaje de éxito.**
   - Le puse `key={status-stage}` para que se reiniciara al cambiar el candidato. Pero el propio PATCH cambia esa `key`, así que el componente se volvía a montar y el aviso "Estado y etapa actualizados" desaparecía.
   - Lo detectó la prueba E2E. Se quitó la `key`: el estado local ya coincide con la respuesta.
2. **Scroll horizontal en móvil.**
   - En un `grid`, los hijos tienen `min-width: auto`, así que la tabla ensanchaba toda la página.
   - Con `grid-cols-1` (`minmax(0, 1fr)`) el scroll queda dentro de la tarjeta de la tabla.
3. **Next.js 16 con `cacheComponents`.**
   - `useSearchParams` y `useParams` (con un `[id]` desconocido en la build) tienen que estar dentro de `<Suspense>`; si no, la build falla.
   - Además, al navegar, Next mantiene la página anterior oculta en el DOM (Activity). En los tests hay que acotar los selectores a la sección visible.

## Verificación

- `npm run lint` y `npm run build` sin errores. `/` se prerenderiza como estático y `/candidates/[id]` con *Partial Prerender*.
- Prueba E2E con Playwright contra la API real (13 comprobaciones):
  - listado sin valores crudos ni notas;
  - filtros reflejados en la URL;
  - validación del formulario y alta de candidato;
  - búsqueda por email sin recarga;
  - PATCH de estado y etapa;
  - añadir y borrar notas;
  - edición persistida tras recargar;
  - borrado del candidato;
  - 404;
  - error de red con "Reintentar";
  - sin scroll horizontal a 390 px.
- El candidato de prueba se crea y se borra en la misma ejecución, porque la API es compartida con el resto del curso.

## Cómo arrancarlo

```bash
cd uis/talent-pipeline-tracker
cp .env.example .env.local
npm install
npm run dev -- --port 3002   # http://localhost:3002
```

No necesita login ni backend propio. El navegador llama directamente a la API mock, que permite CORS desde cualquier origen.
