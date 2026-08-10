# Oportunidad de useMemo detectada e implementada

Fecha: 2026-08-10
Componente: uis/backoffice/src/components/incidents-management-panel.tsx

## Hallazgo

En el render de la tabla de incidencias se hacia trabajo repetitivo en cada fila y en cada render:

1. `updatingIds.includes(incident.id)` por cada fila.
2. Formateo de fecha con `Intl.DateTimeFormat` por fila.

Con listados grandes, este patron incrementa el coste de render innecesariamente.

## Mejora aplicada

Se implemento `useMemo` para construir `incidentRows` con:
- `isUpdating` usando un `Set` (`O(1)` por lookup).
- `nextOptions` precalculado.
- `formattedUpdatedAt` ya transformado.

Tambien se memoizo el formateador de fecha (`dateTimeFormatter`) para no reinstanciarlo continuamente.

## Dependencias del useMemo

`incidentRows` depende de:
- `incidents`
- `updatingIds`
- `dateTimeFormatter`

Estas dependencias son correctas porque cualquier cambio en datos de filas, IDs en actualizacion o formateador debe invalidar el cache.

## Beneficio esperado

- Menos trabajo por render de tabla.
- Mejor escalabilidad cuando aumenta el numero de incidencias.
- Codigo de render mas limpio y declarativo.
