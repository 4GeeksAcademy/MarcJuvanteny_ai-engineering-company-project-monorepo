# Capa de integración con la API de inventario

Implementación de la capa de integración para `/inventory` en el backoffice, siguiendo el patrón de errores y autenticación del proyecto.

## Checklist aplicado

- [x] Crear un módulo centralizado para `/inventory`.
- [x] Garantizar cabecera `Authorization: Bearer <token>` en endpoints protegidos.
- [x] Gestionar errores `4xx` y `5xx` de forma explícita, mostrando mensajes legibles.

## Cambios realizados

- [x] Se creó [uis/backoffice/src/lib/inventory.ts](../uis/backoffice/src/lib/inventory.ts) con:
  - Tipos para productos, entradas, salidas y movimientos de inventario.
  - Método `createInventoryApi(request)` para centralizar todas las llamadas:
    - `listProducts()`
    - `getProduct(productId)`
    - `createProduct(payload)`
    - `createInboundOrder(payload)`
    - `createOutboundOrder(payload)`
    - `listOrders()`
  - Clase `InventoryApiError` para exponer estado HTTP y mensaje de error.
  - Normalización de errores leyendo `detail` del backend con `extractErrorMessage`.

- [x] Se dejó el módulo preparado para conectarse a `authFetch` desde [uis/backoffice/src/lib/auth-context.tsx](../uis/backoffice/src/lib/auth-context.tsx), que ya incluye automáticamente la cabecera Bearer.

## Nota de uso para componentes

Para consumir inventario desde componentes cliente, crear la API con `authFetch` en lugar de llamar a `fetch` directamente:

```ts
const inventoryApi = createInventoryApi(authFetch);
const products = await inventoryApi.listProducts();
```

Con esto, la capa de UI queda desacoplada de detalles HTTP y mantiene una estrategia homogénea de autenticación y errores.
