# Inventario en backoffice: productos y ordenes

Implementacion de pantallas para inventario dentro del backoffice y conexion real con la API `/inventory`.

## Pagina de productos — /inventory/products

- [x] Obtiene y muestra productos con `GET /inventory/products`.
- [x] Renderiza `current_stock` y campos de entidad por fila: `name`, `sku`, `client_name`, `category`, `warehouse`.
- [x] Aplica indicadores visuales de stock:
  - Umbral definido en codigo: `low stock <= 10`, saludable `> 10` (comentado en el componente).
  - Badge visual por color para cada nivel.
- [x] Incluye acciones por fila para crear orden:
  - `Crear entrada` -> `/inventory/orders/inbound?productId=<id>`
  - `Crear salida` -> `/inventory/orders/outbound?productId=<id>`

## Formulario orden de entrada — /inventory/orders/inbound

- [x] Renderiza formulario conectado a `POST /inventory/orders/inbound`.
- [x] Selector de producto por nombre (`name` + `sku`), sin pedir ID bruto al usuario.
- [x] Tras envio exitoso:
  - limpia `quantity` y `reference`
  - muestra mensaje de confirmacion visible
- [x] Ante error `400/500`:
  - muestra mensaje de error de la API en UI
  - nunca se deja solo en consola

## Extra implementado

- [x] Formulario de orden de salida en `/inventory/orders/outbound` conectado a `POST /inventory/orders/outbound`.
- [x] Entrada de menu nueva en sidebar: `Inventario`.

## Archivos creados/modificados

- [x] Nuevo componente [uis/backoffice/src/components/inventory-products-panel.tsx](../uis/backoffice/src/components/inventory-products-panel.tsx)
- [x] Nuevo componente [uis/backoffice/src/components/inventory-inbound-order-panel.tsx](../uis/backoffice/src/components/inventory-inbound-order-panel.tsx)
- [x] Nuevo componente [uis/backoffice/src/components/inventory-outbound-order-panel.tsx](../uis/backoffice/src/components/inventory-outbound-order-panel.tsx)
- [x] Nueva ruta [uis/backoffice/src/app/(protected)/inventory/products/page.tsx](../uis/backoffice/src/app/(protected)/inventory/products/page.tsx)
- [x] Nueva ruta [uis/backoffice/src/app/(protected)/inventory/orders/inbound/page.tsx](../uis/backoffice/src/app/(protected)/inventory/orders/inbound/page.tsx)
- [x] Nueva ruta [uis/backoffice/src/app/(protected)/inventory/orders/outbound/page.tsx](../uis/backoffice/src/app/(protected)/inventory/orders/outbound/page.tsx)
- [x] Navegacion actualizada en [uis/backoffice/src/components/backoffice-shell.tsx](../uis/backoffice/src/components/backoffice-shell.tsx)
- [x] Estilos de stock y acciones inline en [uis/backoffice/src/app/globals.css](../uis/backoffice/src/app/globals.css)
