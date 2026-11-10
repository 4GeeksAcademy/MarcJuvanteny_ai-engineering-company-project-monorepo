# Candidatos de Lazy Loading en website Next.js

Fecha: 2026-08-10
Alcance revisado: uis/website/src/app y uis/website/src/components

## Resumen

Se identifican dos candidatos claros para diferir carga con lazy loading:

1. `LandingInteractions` en la ruta principal `/`
2. `QuoteForm` en la ruta `/application`

Ambos son componentes de cliente con logica interactiva y estado, por lo que mueven JS al navegador. Diferir su carga reduce JS inicial y mejora tiempo de interaccion en el primer render.

## Candidato 1: LandingInteractions (ruta `/`)

Ubicacion de evidencia:
- Importado en `uis/website/src/app/page.tsx` (linea 2).
- Renderizado al final de la landing en `uis/website/src/app/page.tsx` (linea 285).
- Logica interna en `uis/website/src/components/landing-interactions.tsx` (lineas 1-146).

Por que es buen candidato:
- Es un componente 100% cliente (`"use client"`) que no aporta HTML critico para SEO.
- Inicializa listeners de scroll, `IntersectionObserver`, animacion de contadores y carrusel automatico.
- Parte de su funcionalidad es progresiva y puede empezar unos milisegundos despues del contenido principal sin degradar la comprension de la pagina.

Justificacion para diferir carga:
- El contenido visible de la landing (hero, servicios, textos) ya llega desde servidor.
- Si se difiere este script, el usuario puede leer y navegar antes de descargar/ejecutar toda la logica de animaciones.
- Esto reduce trabajo de hidratacion inicial y suele mejorar TTI/TBT en dispositivos medios.

Estrategia sugerida:
- Import dinamico con `next/dynamic` y `ssr: false` para cargar el componente solo en cliente.
- Opcional: activarlo tras `requestIdleCallback` o tras primer scroll para empujar aun mas lejos su coste.

## Candidato 2: QuoteForm (ruta `/application`)

Ubicacion de evidencia:
- Importado y renderizado desde `uis/website/src/app/application/page.tsx` (lineas 3 y 69).
- Definido como componente cliente en `uis/website/src/components/quote-form.tsx` (linea 1).
- Incluye multiples estados, validaciones por campo y handlers de submit/reset (lineas 112-220 y siguientes).

Por que es buen candidato:
- Tiene bastante logica de validacion y estados de formulario en cliente.
- No es necesario para pintar cabecera, metadata ni contexto visual inicial de la ruta.
- En visitas donde el usuario aun no interactua, cargar todo el JS del formulario al instante no es estrictamente necesario.

Justificacion para diferir carga:
- Permite priorizar el render del layout y copy de la pagina.
- El formulario puede cargarse bajo demanda (cuando entra en viewport o cuando el usuario hace focus/click en la zona del formulario).
- Reduce el peso inicial de JS y reparte el coste de ejecucion donde realmente hay intencion de uso.

Estrategia sugerida:
- Import dinamico con `next/dynamic` para `QuoteForm`.
- Mostrar skeleton liviano hasta que llegue el bundle del formulario.
- Si se busca experiencia inmediata al usuario activo, precargar el chunk al detectar hover/tap sobre CTA "Calcular presupuesto".

## Prioridad recomendada

1. Aplicar lazy loading a `LandingInteractions` primero (alto impacto, bajo riesgo funcional).
2. Aplicar lazy loading a `QuoteForm` segundo (alto impacto potencial, validar UX de carga con skeleton).

## Riesgos a vigilar

- No romper accesibilidad del formulario durante el estado de carga.
- Evitar layout shift visible al montar componentes diferidos.
- Medir antes/despues con Lighthouse o Web Vitals para confirmar mejora real.
