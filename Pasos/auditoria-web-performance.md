# Auditoría de web performance + refactorización de frontends

Fecha inicio: 2026-08-27
Alcance: `uis/website` (web corporativa) y `uis/backoffice` (backoffice)
Documentos relacionados: [`AUDIT.md`](../AUDIT.md), [`audit/before/`](../audit/before/README.md), [`audit/after/`](../audit/after/README.md)

---

## Estado global

| Bloque | Estado |
|---|---|
| Medición inicial (Lighthouse before) | ⛔ Bloqueado — sin Chrome en el Codespace |
| Análisis del código → `AUDIT.md` | ✅ Hecho (2 casos documentados) |
| Instalación de skills de agente | ⏳ Pendiente (opcional, decisión CTO) |
| Correcciones | 🟡 Parcial — 1 refactor aplicado; KPI Lighthouse pendientes de medición |
| Medición final (Lighthouse after) | ⛔ Bloqueado — depende de la medición inicial |

---

## 1) Medición inicial — ⛔ BLOQUEADO

- `google-chrome` / `chromium` **no están instalados** en este Codespace y
  `npx lighthouse` no puede descargarse en modo no interactivo.
- Además el backoffice necesita la API `incidents-api` en `:8001` + Supabase para
  renderizar el dashboard con datos.
- **Acción para Marc:** ejecutar Lighthouse desde una máquina con Chrome siguiendo
  `audit/before/README.md`, guardar capturas en `audit/before/` y hacer commit.

## 2) Análisis del código — ✅ HECHO

`AUDIT.md` creado en la raíz con 2 casos de repetición:

1. **Ciclo de envío duplicado en formularios de auth** (`login`, `register`,
   `forgot-password`, `reset-password`) → Custom Hook `useApiSubmit`.
2. **Bloque "campo + label + error" repetido** en `quote-form.tsx` (website, ~13×)
   y `register-form.tsx` (backoffice, 6×) → componente `<FormField>`.

Observaciones secundarias anotadas en `AUDIT.md` (imágenes `<img>` remotas sin
dimensiones en el hero de website = riesgo LCP/CLS; `next/font` sin `swap`; etc.).

## 3) Instalación de skills de agente — ⏳ PENDIENTE

- Skills indicadas por el CTO (instalar solo "en caso de necesitarlo"):
  - `https://www.skills.sh/addyosmani/web-quality-skills/core-web-vitals`
  - `https://www.skills.sh/addyosmani/web-quality-skills/performance`
  - `https://www.skills.sh/cloudflare/skills/web-perf`
- No instaladas todavía. Tienen sentido una vez haya un informe Lighthouse real
  que interpretar (KPI por KPI).

## 4) Correcciones

### 4a) Refactorizaciones del análisis de código

- [x] **Custom Hook `useApiSubmit`** creado en
      `uis/backoffice/src/lib/use-api-submit.ts`.
- [x] Aplicado a `uis/backoffice/src/components/forgot-password-form.tsx`.
- [x] Aplicado a `uis/backoffice/src/components/reset-password-form.tsx`.
- [ ] Aplicar a `login-form.tsx` (cuida la interacción con `useAuth().login`).
- [ ] Aplicar a `register-form.tsx`.
- [ ] Extraer componente `<FormField>` (caso 2 de `AUDIT.md`).

> Verificación pendiente: no hay `node_modules` en `uis/backoffice`, así que no se
> ha podido correr `npm run lint` ni `npm run build`. Antes de commitear:
> `cd uis/backoffice && npm install && npm run lint && npm run build`.

### 4b) Correcciones de KPI (TTFB, LCP, CLS, INP, Performance)

- [ ] Pendiente de la medición inicial. Orden previsto una vez haya números:
  1. LCP/CLS del hero de `uis/website` (imágenes remotas sin `width`/`height` →
     `next/image` o dimensiones explícitas).
  2. `next/font` con `display: "swap"`.
  3. `LandingInteractions` con `ssr: false` + `requestIdleCallback`
     (ver `lazy-loading-candidatos-nextjs.md`).
  4. Re-ejecutar Lighthouse en la misma URL tras cada cambio (un problema por commit).

## 5) Medición final — ⛔ BLOQUEADO

Depende de (1). Repetir ejecuciones y rellenar la tabla comparativa de
`audit/after/README.md`.

---

## Próximo paso inmediato

1. Marc: correr Lighthouse before en local con Chrome → `audit/before/` + commit.
2. Con el informe, decidir si instalar las skills del CTO.
3. Seguir con las correcciones de KPI, una por commit, remidiendo cada vez.
