# Talent Pipeline Tracker (Hito 3)

Frontend de RRHH para seguir el proceso de selección del puesto **Asistente de Dirección, sede Zaragoza** (`CONTEXT/CONTEXT3.md`). Consume la API mock del curso:

- Documentación: https://playground.4geeks.com/tracker/api/v1/docs
- URL base: `https://playground.4geeks.com/tracker/api/v1`

Stack: Next.js 16 (App Router) + React 19 + TypeScript + Tailwind CSS 4. Solo hooks de React; no hay librería de estado global.

## Arrancar

```bash
cd uis/talent-pipeline-tracker
cp .env.example .env.local   # NEXT_PUBLIC_API_URL
npm install
npm run dev                  # http://localhost:3000
```

Para otro puerto: `npm run dev -- --port 3002`. Comprobaciones: `npm run lint` y `npm run build`.

## Rutas

| Ruta | Qué hace |
|---|---|
| `/` | Listado (nombre, puesto, estado, etapa). Filtros por estado y etapa, y búsqueda por nombre o email sin recargar; todo queda en la URL (`?status=&stage=&search=&page=`). Alta de candidato en un modal. |
| `/candidates/[id]` | Detalle: datos, edición (PUT), cambio de estado y etapa (PATCH), notas (añadir y borrar) y borrado del candidato. |

## Estructura

```
src/
  app/            páginas (page.tsx, candidates/[id]/page.tsx) y layout
  components/     listado, filtros, tabla, formulario, detalle, notas, feedback
  lib/api.ts      cliente de la API (fetch + mensajes de error en español)
  lib/labels.ts   valores de la API -> etiquetas en español
  types/          tipos del contrato de la API
```

## Decisiones

- **Los valores en inglés de la API nunca llegan a la pantalla.** Todo pasa por `lib/labels.ts`. Si la API devolviera un valor desconocido, se muestra "Estado desconocido" en vez del valor crudo.
- **Las notas solo se ven en el detalle.** Aunque `GET /records` también devuelve las notas, el listado no las usa; el detalle las pide con `GET /records/{id}/notes`.
- **El formulario incluye todos los campos de `RecordCreate`.** Obligatorios: nombre, email, teléfono, puesto y años de experiencia. Opcionales: LinkedIn y CV. Se validan en el cliente antes de enviar, y los errores 422 de la API se traducen a nombres de campo en español.
- **Búsqueda con debounce de 300 ms.** Se actualiza la URL con `router.replace`, sin recargar la página. Las peticiones anteriores se cancelan con `AbortController`, así que una respuesta lenta no puede pisar a una más nueva.
- **Cada operación tiene estado de carga, éxito y error.** Cuando falla la carga hay un botón "Reintentar".
- **Los enlaces de LinkedIn y CV solo se muestran si son `http(s)`.**
- **Datos compartidos.** La API mock es común a todo el curso, así que el listado incluye candidatos de otros puestos.
