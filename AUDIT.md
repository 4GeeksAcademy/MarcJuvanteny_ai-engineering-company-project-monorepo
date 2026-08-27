# AUDIT.md — Auditoría de rendimiento web y análisis de código

Fecha: 2026-08-27
Alcance revisado: `uis/website/` (web corporativa) y `uis/backoffice/` (backoffice interno)
Seguimiento operativo: `Pasos/auditoria-web-performance.md` · Correcciones: `REPORT.md`

Restricción de la auditoría: **no se reestructura la arquitectura de ningún frontend**.
Solo correcciones dirigidas + las dos extracciones de código identificadas abajo.

---

## 1. Puntuaciones iniciales de Lighthouse

> ⚠️ Este Codespace no tiene Chrome instalado y `npx lighthouse` no puede
> descargarse en modo no interactivo; el backoffice además necesita la API
> `incidents-api` en `:8001`. Las ejecuciones se hacen desde una máquina con
> Chrome siguiendo `audit/before/README.md`. Rellenar esta tabla con esos
> resultados y adjuntar capturas en `audit/before/`.

### Web corporativa (`uis/website`)

| Página | Modo | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|---|
| `/` (inicio) | escritorio | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| `/` (inicio) | móvil | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| `/application` | escritorio | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |
| `/application` | móvil | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |

### Backoffice (`uis/backoffice`)

| Página | Modo | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|---|
| `/` (dashboard principal) | escritorio | _pendiente_ | _pendiente_ | _pendiente_ | _pendiente_ |

Métricas de laboratorio a registrar junto a cada fila: **TTFB, LCP, CLS, INP/TBT**.

---

## 2. Problemas identificados y causa raíz

Detectados por revisión de código (`uis/website/src` y `uis/backoffice/src`).
Cada uno se confirmará y priorizará con el informe Lighthouse real.

### P1 — Imágenes del hero y de secciones sin dimensiones ni optimización · KPI: LCP, CLS

- **Dónde:** `uis/website/src/app/page.tsx` (hero `img.hero-photo` línea ~112;
  `services-img`, `photo-strip`, `carousel-media`) y
  `uis/website/src/app/application/page.tsx`.
- **Síntoma esperado:** LCP alto (la imagen del hero es el elemento LCP probable)
  y CLS al reflowear cuando cargan las imágenes.
- **Causa raíz:** se usa `<img>` nativo apuntando a URLs remotas de
  `images.unsplash.com` **sin `width`/`height`**, sin `loading`/`fetchpriority`
  explícitos y sin `next/image`. El navegador no puede reservar el hueco →
  layout shift; y descarga imágenes a resolución completa sin `srcset` →
  transferencia grande en la ruta crítica.
- **Corrección dirigida (sin reescritura):** añadir `width`/`height` (o
  `aspect-ratio` en CSS) a cada `<img>`; `fetchpriority="high"` +
  `loading="eager"` solo en la imagen del hero y `loading="lazy"` en el resto;
  valorar `next/image` con `remotePatterns` para `images.unsplash.com` si el
  margen lo justifica.

### P2 — Fuentes web sin estrategia de `swap` · KPI: LCP, CLS (FOIT)

- **Dónde:** `uis/website/src/app/layout.tsx` y `uis/backoffice/src/app/layout.tsx`
  (`DM_Sans`, `Space_Grotesk` vía `next/font/google`).
- **Causa raíz:** no se pasa `display: "swap"` a `next/font`; por defecto usa
  `font-display: optional`/bloqueo breve que puede retrasar el primer texto
  pintado o provocar un pequeño shift al intercambiar la fuente.
- **Corrección dirigida:** `DM_Sans({ subsets: ["latin"], display: "swap", variable: ... })`
  en ambos layouts.

### P3 — JS de interacciones de la landing en la ruta crítica de hidratación · KPI: INP/TBT

- **Dónde:** `uis/website/src/components/landing-interactions.tsx` (146 líneas:
  listeners de scroll, 2× `IntersectionObserver`, animación de contadores por
  `requestAnimationFrame`, carrusel con `rAF` en bucle continuo).
- **Estado actual:** ya se carga con `next/dynamic` desde `page.tsx`, **pero sin
  `ssr: false`** y sin diferir el arranque.
- **Causa raíz:** todo el trabajo se engancha en el primer `useEffect` tras la
  hidratación; el bucle de `requestAnimationFrame` del carrusel corre siempre,
  compitiendo por el hilo principal y penalizando INP en equipos medios.
- **Corrección dirigida:** `next/dynamic(..., { ssr: false })` + arrancar la
  lógica no crítica (carrusel, contadores) tras `requestIdleCallback` /
  primer scroll. No cambia la arquitectura del componente.
  Ref: `Pasos/lazy-loading-candidatos-nextjs.md`.

### P4 — `new Date()` por pulsación en la validación del formulario · KPI: INP (menor)

- **Dónde:** `uis/website/src/components/quote-form.tsx`, `validateField`
  caso `"pickupDate"` (líneas ~225-232): crea dos `Date` en cada `onChange`.
- **Causa raíz:** `validateField` se invoca en cada tecleo vía `setValue`; el
  coste es bajo pero es trabajo evitable en el handler de entrada.
- **Corrección dirigida:** calcular "hoy" una vez (fuera del `switch` o
  memoizado) y reutilizarlo.

### P5 — Dashboard del backoffice hace trabajo de negocio en cada render · KPI: TTFB/TBT

- **Dónde:** `uis/backoffice/src/app/(protected)/page.tsx` →
  `getHito2DashboardResult()` en el cuerpo del componente, y
  `incidents-management-panel.tsx` (ver `Pasos/usememo-oportunidad-incidents-panel.md`,
  ya mitigado con `useMemo`).
- **Causa raíz:** el cálculo del dashboard (`inventoryValueUSD`, `lowStockSkus`,
  `recommendedCarrier`, `categoryCount`) se ejecuta síncrono en render sin
  memoización ni cacheo.
- **Corrección dirigida:** memoizar el resultado / moverlo a datos precomputados;
  sin rediseñar el módulo Hito 2.

### P6 — Accesibilidad frágil por marcado de campo copiado a mano · KPI: Accessibility

- **Dónde:** `uis/website/src/components/quote-form.tsx` (~13 campos) y
  formularios de auth del backoffice.
- **Causa raíz:** cada campo repite manualmente `aria-invalid`, `role="alert"`,
  `aria-live="polite"`; un copiado incompleto degrada la accesibilidad sin aviso.
- **Corrección dirigida:** ver **Caso 2** del análisis de refactorización (`<FormField>`).

---

## 3. Análisis de refactorización

### Caso 1 — Ciclo de envío duplicado en los formularios de autenticación (Custom Hook)

#### Dónde aparece

| Archivo | Líneas aprox. | Repetición |
|---|---|---|
| `uis/backoffice/src/components/login-form.tsx` | 12-31 | `isSubmitting` + `errorMessage` + `try/catch/finally` |
| `uis/backoffice/src/components/register-form.tsx` | 33-92 | mismo patrón + `response.json().catch(() => null)` |
| `uis/backoffice/src/components/forgot-password-form.tsx` | 10-46 | mismo patrón |
| `uis/backoffice/src/components/reset-password-form.tsx` | 16-63 | mismo patrón |

Los cuatro repiten esta secuencia:

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

#### Por qué es candidato

- Es **lógica de estado**, no marcado: encaja en un Custom Hook.
- La única variación real es *qué* `fetch`/`timedFetch` se lanza; el resto es
  idéntico y propenso a divergir (olvidar el `finally` deja `isSubmitting` en `true`).
- No toca la arquitectura: cada componente sigue siendo el mismo, solo delega el
  ciclo de envío.

#### Abstracción compartida

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

El hook centraliza: `isSubmitting=true` + limpiar error al empezar, bajar el flag
al terminar, y traducir cualquier `throw` a mensaje de banner. Si la acción setea
un error de campo y hace `return` (4xx controlado), ese mensaje se conserva.

#### Estado

- [x] Hook creado: `uis/backoffice/src/lib/use-api-submit.ts`
- [x] Aplicado a `forgot-password-form.tsx`
- [x] Aplicado a `reset-password-form.tsx`
- [ ] Pendiente: `login-form.tsx` y `register-form.tsx` (interacción con
      `useAuth().login`; un problema por commit).

---

### Caso 2 — Bloque "campo con label + error" repetido en ambos frontends (Componente)

#### Dónde aparece

| Archivo | Repeticiones | Estructura repetida |
|---|---|---|
| `uis/website/src/components/quote-form.tsx` | ~13 (líneas 331-428) | `<div><label/><input/><p role="alert">{errors.x}</p></div>` |
| `uis/backoffice/src/components/register-form.tsx` | 6 (líneas 100-170) | `<label className="field-block"><span/>...<input/><span className="field-error">` |
| `uis/backoffice/src/components/login-form.tsx` | 2 | `<label className="field-block"><span/><input/></label>` |
| `uis/backoffice/src/components/reset-password-form.tsx` | 2 | idem |
| `uis/backoffice/src/components/forgot-password-form.tsx` | 1 | idem |

En ambos frontends se repite el mismo patrón conceptual: **label + control +
slot de error por campo**. En `quote-form.tsx` se repite 13 veces el mismo
`<p className="mt-2 text-sm text-red-300" role="alert" aria-live="polite">`.

#### Por qué es candidato

- El bloque mezcla accesibilidad (`aria-invalid`, `role="alert"`, `aria-live`)
  que hoy hay que recordar copiar en cada campo → degradación silenciosa (P6).
- 13 repeticiones casi idénticas en un archivo hacen el formulario difícil de
  mantener.
- El "shape" es el mismo en las dos apps aunque las clases difieran (Tailwind
  utilitario en `website`, clases semánticas en `backoffice`).

#### Abstracción compartida

Un componente `<FormField>` por frontend (misma API, estilos propios):

```tsx
<FormField id="email" label="Email *" error={errors.email}>
  {(fieldProps) => (
    <input type="email" autoComplete="email" {...fieldProps}
           value={formData.email}
           onChange={(e) => setValue("email", e.target.value)} />
  )}
</FormField>
```

`<FormField>` renderiza `<label htmlFor>`, el contenedor, el `<p>`/`<span>` de
error con `role="alert"` + `aria-live`, y pasa `aria-invalid` + `id` al control.
Ubicación: `uis/backoffice/src/components/form-field.tsx` y
`uis/website/src/components/form-field.tsx`.

> No se coloca en `packages/shared`: `uis/website` no tiene
> `experimental.externalDir` y son dos proyectos npm separados. Compartir el
> componente de verdad exigiría tocar `next.config.ts` de `website`, lo que
> entraría en "reestructurar", fuera del alcance de esta auditoría.

#### Estado

- [ ] Pendiente de implementar (identificado, no aplicado todavía).
