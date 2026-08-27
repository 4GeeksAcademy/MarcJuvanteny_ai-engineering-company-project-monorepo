# REPORT.md — Correcciones aplicadas y comparativa

Fecha: 2026-08-27
Relacionado: `AUDIT.md` (análisis) · `Pasos/auditoria-web-performance.md` (seguimiento)
Restricción respetada: **sin reestructurar la arquitectura de ningún frontend**;
solo correcciones dirigidas.

---

## 1. Correcciones aplicadas

### C1 — Extracción del ciclo de envío de los formularios de auth a un Custom Hook

- **Problema de origen:** `AUDIT.md` §3 Caso 1 — cuatro formterios del backoffice
  (`login`, `register`, `forgot-password`, `reset-password`) repetían el mismo
  bloque de `isSubmitting` + `errorMessage` + `try/catch/finally`.
- **Cambio:**
  - Nuevo `uis/backoffice/src/lib/use-api-submit.ts` → hook `useApiSubmit()` que
    devuelve `{ isSubmitting, errorMessage, setErrorMessage, submit }`.
    `submit(action)` pone `isSubmitting=true` y limpia el error al empezar, lo
    baja al terminar y convierte cualquier `throw` en mensaje de banner;
    respeta un error de campo seteado antes de un `return` (4xx controlado).
  - `uis/backoffice/src/components/forgot-password-form.tsx` → usa el hook;
    elimina 3 `useState` y el `try/catch/finally` manual. Se conserva el estado
    propio `isSubmitted` y el mensaje de red "No se pudo conectar con la API."
    (se lanza explícitamente para no exponer el error crudo de `fetch`).
  - `uis/backoffice/src/components/reset-password-form.tsx` → íd. Se conservan
    las validaciones previas (contraseñas coinciden, token presente) y la
    rama de "enlace inválido".
- **Alcance:** puramente interno de esos dos componentes + un archivo nuevo. No
  cambia rutas, contratos, API ni el árbol de componentes.
- **Impacto en KPI de rendimiento:** nulo/indirecto (menos JS duplicado tras
  minificar, marginal). El valor es de mantenibilidad y de reducir la superficie
  de bugs de estado.
- **Verificación:** ⏳ pendiente `npm install && npm run lint && npm run build`
  en `uis/backoffice` (no hay `node_modules` en el Codespace).

### C2..Cn — Correcciones de KPI (LCP / CLS / INP / TTFB)

⏳ **Pendientes de la medición inicial de Lighthouse.** Plan, una por commit,
remidiendo la misma URL tras cada cambio (orden por impacto esperado):

| # | Corrección | Problema (`AUDIT.md`) | KPI objetivo | Archivos |
|---|---|---|---|---|
| C2 | `width`/`height` + `fetchpriority`/`loading` en `<img>` del hero y secciones | P1 | LCP, CLS | `uis/website/src/app/page.tsx`, `.../application/page.tsx` |
| C3 | `display: "swap"` en `next/font` | P2 | LCP, CLS | ambos `layout.tsx` |
| C4 | `next/dynamic(..., { ssr:false })` + arranque diferido de carrusel/contadores | P3 | INP, TBT | `uis/website/src/app/page.tsx`, `landing-interactions.tsx` |
| C5 | "hoy" calculado una vez en `validateField` | P4 | INP | `uis/website/src/components/quote-form.tsx` |
| C6 | Memoizar `getHito2DashboardResult()` | P5 | TBT | `uis/backoffice/src/app/(protected)/page.tsx` |
| C7 | `<FormField>` (label + error + aria) | P6 / Caso 2 | Accessibility | `quote-form.tsx`, `register-form.tsx` |

---

## 2. Comparativa antes / después

⏳ **Pendiente de mediciones.** Rellenar desde `audit/before/` y `audit/after/`.

### Web corporativa (`uis/website`)

| Página | Modo | Perf antes | Perf después | LCP antes | LCP después | CLS antes | CLS después | INP/TBT antes | INP/TBT después | TTFB antes | TTFB después |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/` | escritorio | | | | | | | | | | |
| `/` | móvil | | | | | | | | | | |
| `/application` | escritorio | | | | | | | | | | |
| `/application` | móvil | | | | | | | | | | |

### Backoffice (`uis/backoffice`)

| Página | Modo | Perf antes | Perf después | LCP antes | LCP después | CLS antes | CLS después | INP/TBT antes | INP/TBT después | TTFB antes | TTFB después |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/` | escritorio | | | | | | | | | | |

---

## 3. Valoración de qué tuvo mayor impacto

⏳ **A completar tras la medición final.** Hipótesis previa a datos:

1. **C2 (imágenes del hero con dimensiones + `fetchpriority`)** debería dar el
   mayor salto: ataca a la vez el elemento LCP más probable de `website /` y la
   mayor fuente de CLS. Bajo riesgo, cero cambios de arquitectura.
2. **C4 (diferir `landing-interactions`)** debería mover INP/TBT en móvil, donde
   el bucle de `requestAnimationFrame` del carrusel pesa más.
3. **C3 (`font-display: swap`)** aporta una mejora pequeña y consistente en LCP.
4. **C1 (hook `useApiSubmit`)** no mueve KPI de rendimiento; su impacto es de
   calidad de código.

Confirmar/ajustar este ranking con los números reales de `audit/after/`.
