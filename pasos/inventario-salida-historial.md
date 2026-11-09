# Inventario: orden de salida y historial de ordenes

Implementacion del formulario de salida con salvaguardas de stock y de la pagina de historial en solo lectura.

## Formulario de orden de salida — /inventory/orders/outbound

- [x] Envia datos a `POST /inventory/orders/outbound`.
- [x] Al seleccionar producto, muestra `current_stock` de forma reactiva.
- [x] Si la cantidad supera el stock mostrado, presenta advertencia de UX en cliente antes del envio.
- [x] Maneja `HTTP 400` de API (stock insuficiente) con mensaje inline junto al campo de cantidad.

## Pagina historial de ordenes — /inventory/orders

- [x] Obtiene y muestra ordenes desde `GET /inventory/orders`.
- [x] Cada fila muestra: nombre del producto, cantidad, tipo (entrada/salida), fecha de creacion y `user_uuid`.
- [x] Distingue visualmente entradas y salidas con badge por color y etiqueta.
- [x] Vista de solo lectura: sin acciones de borrado ni edicion.

## Archivos creados/modificados

- [x] Modificado [uis/backoffice/src/components/inventory-outbound-order-panel.tsx](../uis/backoffice/src/components/inventory-outbound-order-panel.tsx)
- [x] Creado [uis/backoffice/src/components/inventory-orders-history-panel.tsx](../uis/backoffice/src/components/inventory-orders-history-panel.tsx)
- [x] Creado [uis/backoffice/src/app/(protected)/inventory/orders/page.tsx](../uis/backoffice/src/app/(protected)/inventory/orders/page.tsx)
- [x] Modificado [uis/backoffice/src/components/inventory-products-panel.tsx](../uis/backoffice/src/components/inventory-products-panel.tsx) para enlazar al historial
- [x] Modificado [uis/backoffice/src/app/globals.css](../uis/backoffice/src/app/globals.css) con estilos de warning y badges de movimiento
