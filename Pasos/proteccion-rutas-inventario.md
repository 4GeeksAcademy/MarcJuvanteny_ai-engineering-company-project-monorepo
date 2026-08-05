# Proteccion de rutas de inventario

Aplicacion del patron de autenticacion existente del backoffice para las 4 paginas de inventario.

## Requisito

- [x] Las cuatro paginas de inventario redirigen a usuarios no autenticados a login usando el patron ya existente.

## Implementacion aplicada

- [x] Se reutiliza el guard global del segmento protegido en [uis/backoffice/src/app/(protected)/layout.tsx](../uis/backoffice/src/app/(protected)/layout.tsx).
- [x] Ese layout usa [uis/backoffice/src/components/auth-guard.tsx](../uis/backoffice/src/components/auth-guard.tsx), que:
  - si estado es unauthenticated ejecuta `router.replace("/login")`
  - solo renderiza contenido cuando estado es authenticated

## Cobertura de rutas verificadas

- [x] [uis/backoffice/src/app/(protected)/inventory/products/page.tsx](../uis/backoffice/src/app/(protected)/inventory/products/page.tsx)
- [x] [uis/backoffice/src/app/(protected)/inventory/orders/inbound/page.tsx](../uis/backoffice/src/app/(protected)/inventory/orders/inbound/page.tsx)
- [x] [uis/backoffice/src/app/(protected)/inventory/orders/outbound/page.tsx](../uis/backoffice/src/app/(protected)/inventory/orders/outbound/page.tsx)
- [x] [uis/backoffice/src/app/(protected)/inventory/orders/page.tsx](../uis/backoffice/src/app/(protected)/inventory/orders/page.tsx)

Resultado: todas las paginas quedan protegidas con el mismo patron de auth del backoffice, sin duplicar logica.
