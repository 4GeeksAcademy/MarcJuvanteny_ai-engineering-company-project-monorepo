# AUDIT.md — Auditoría de rendimiento web y análisis de código

Fecha: 2026-08-27
Alcance revisado: `uis/website/` (web corporativa) y `uis/backoffice/` (backoffice interno)

Este documento cubre el **análisis de código** de la auditoría: casos de repetición
de componentes o lógica que se pueden extraer a un componente compartido o a un
Custom Hook. Las mediciones de Lighthouse (antes/después) viven en `audit/before/`
y `audit/after/`; el seguimiento operativo está en `Pasos/auditoria-web-performance.md`.

---

## Caso 1 — Ciclo de envío duplicado en los formularios de autenticación (Custom Hook)

### Dónde aparece

| Archivo | Líneas aprox. | Repetición |
|---|---|---|
| `uis/backoffice/src/components/login-form.tsx` | 12-31 | `isSubmitting` + `errorMessage` + `try/catch/finally` |
| `uis/backoffice/src/components/register-form.tsx` | 33-92 | mismo patrón + `response.json().catch(() => null)` |
| `uis/backoffice/src/components/forgot-password-form.tsx` | 10-46 | mismo patrón |
| `uis/backoffice/src/components/reset-password-form.tsx` | 16-63 | mismo patrón |

Los cuatro componentes repiten exactamente esta secuencia:

```tsx
const [isSubmitting, setIsSubmitting] = useState(false);
const [errorMessage, setErrorMessage] = useState<string | null>(null);

async function onSubmit(event) {
  event.preventDefault();
  setIsSubmitting(true);
  setErrorMessage(null);
  try {
    // ... la única parte que cambia: qué petición se hace
  } catch (error) {
    setErrorMessage(error instanceof Error ? error.message : "No se pudo conectar con la API.");
  } finally {
    setIsSubmitting(false);
  }
}
```

### Por qué es candidato a refactorización

- Es **lógica de estado**, no marcado: encaja de forma natural en un Custom Hook.
- La única variación real entre formularios es *qué* `fetch`/`timedFetch` se lanza;
  toda la gestión de `isSubmitting`, limpieza de error, captura y mensaje de
  fallback es idéntica y propensa a divergir (p. ej. olvidar el `finally`).
- Reduce superficie de bug: hoy cada formulario podría dejar `isSubmitting` en
  `true` si alguien añade un `return` temprano mal colocado.

### Cómo queda la abstracción compartida

`uis/backoffice/src/lib/use-api-submit.ts`:

```ts
const { isSubmitting, errorMessage, setErrorMessage, submit } = useApiSubmit();

await submit(async () => {
  const response = await timedFetch(/* ... */);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    setErrorMessage(extractErrorMessage(data, "..."));
    return; // el hook respeta este mensaje y no lo limpia
  }
  // camino feliz
});
```

El hook centraliza: poner `isSubmitting=true` y limpiar error al empezar,
bajar el flag al terminar, y capturar cualquier `throw` traduciéndolo a mensaje
de banner. Si la acción setea un error de campo y hace `return` (4xx controlado),
ese mensaje se conserva.

### Estado

- [x] Hook creado: `uis/backoffice/src/lib/use-api-submit.ts`
- [x] Aplicado a `forgot-password-form.tsx`
- [x] Aplicado a `reset-password-form.tsx`
- [ ] Pendiente: `login-form.tsx` y `register-form.tsx` (se dejan para commits
      posteriores por la interacción con `useAuth().login` — un problema por commit).

---

## Caso 2 — Bloque "campo con label + error" repetido en ambos frontends (Componente)

### Dónde aparece

| Archivo | Repeticiones | Estructura repetida |
|---|---|---|
| `uis/website/src/components/quote-form.tsx` | ~13 (líneas 331-428) | `<div><label/><input/><p role="alert">{errors.x}</p></div>` |
| `uis/backoffice/src/components/register-form.tsx` | 6 (líneas 100-170) | `<label className="field-block"><span/>...<input/><span className="field-error">` |
| `uis/backoffice/src/components/login-form.tsx` | 2 | `<label className="field-block"><span/><input/></label>` |
| `uis/backoffice/src/components/reset-password-form.tsx` | 2 | idem |
| `uis/backoffice/src/components/forgot-password-form.tsx` | 1 | idem |

En ambos frontends se repite el mismo patrón conceptual: **label + control +
slot de error por campo**. En `quote-form.tsx` incluso se repite 13 veces el
mismo `<p className="mt-2 text-sm text-red-300" role="alert" aria-live="polite">`.

### Por qué es candidato a refactorización

- El bloque mezcla accesibilidad (`aria-invalid`, `role="alert"`, `aria-live`)
  que hoy hay que recordar copiar en cada campo; si un campo se copia mal, se
  degrada la accesibilidad de forma silenciosa.
- 13 repeticiones casi idénticas en un solo archivo (`quote-form.tsx`) hacen el
  formulario difícil de leer y de mantener.
- El "shape" es el mismo en las dos apps aunque el sistema de clases difiera
  (Tailwind utilitario en `website`, clases semánticas en `backoffice`).

### Cómo queda la abstracción compartida

Un componente `<FormField>` por frontend (misma API, estilos propios de cada app):

```tsx
<FormField
  id="email"
  label="Email *"
  error={errors.email}
>
  {(fieldProps) => (
    <input type="email" autoComplete="email" {...fieldProps}
           value={formData.email}
           onChange={(e) => setValue("email", e.target.value)} />
  )}
</FormField>
```

`<FormField>` se encarga de: renderizar `<label htmlFor>`, el contenedor, el
`<p>`/`<span>` de error con `role="alert"` + `aria-live`, y pasar
`aria-invalid` + `id` al control. En `backoffice` se puede publicar como
`uis/backoffice/src/components/form-field.tsx`; en `website` como
`uis/website/src/components/form-field.tsx`.

> Nota: no se coloca en `packages/shared` porque `uis/website` no tiene
> `experimental.externalDir` habilitado y son dos proyectos npm separados sin
> workspace. Compartir de verdad el componente exigiría tocar `next.config.ts`
> de `website` (fuera del alcance "un problema por commit" de esta auditoría).

### Estado

- [ ] Pendiente de implementar (identificado, no aplicado todavía).

---

## Observaciones secundarias (no bloquean KPI, anotar y priorizar después)

- `uis/website/src/app/page.tsx`: `<img>` de Unsplash en `<img>` nativo con URLs
  remotas y sin `width`/`height` ni `next/image` → riesgo de CLS y LCP alto en la
  imagen del hero. Candidato #1 real para el KPI de LCP/CLS.
- `landing-interactions.tsx`: ya se difiere con `next/dynamic`, pero sin
  `ssr: false` ni disparo por `requestIdleCallback` (ver
  `Pasos/lazy-loading-candidatos-nextjs.md`).
- `quote-form.tsx`: `new Date()` dentro de `validateField` en cada pulsación de
  tecla del campo fecha; barato pero evitable.
- Fuentes: ambas apps cargan `DM_Sans` + `Space_Grotesk` vía `next/font/google`
  (bien), pero sin `display: "swap"` explícito.
