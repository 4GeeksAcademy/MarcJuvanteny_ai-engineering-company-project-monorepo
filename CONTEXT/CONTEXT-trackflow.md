# CONTEXT — TrackFlow

## Proyectos de Telemetria (Plan · Captura · Almacenamiento · Reporte)

Este documento consolida el contexto funcional y de negocio para implementar la telemetria del sistema de inventario de TrackFlow.

---

## 1. Compania

TrackFlow gestiona almacenes y ultima milla para marcas de moda, electronica y cosmetica, operando entre Los Angeles y Zaragoza.

El sistema de inventario es el nucleo operativo de la compania:

- stock por SKU
- stock por cliente
- stock por almacen

En TrackFlow, el inventario es el negocio. El plan de telemetria, su captura, almacenamiento y reporte deben centrarse en este sistema para habilitar:

- dashboard operativo de Ana (operaciones de almacen)
- dashboard ejecutivo de Thomas (comparativas globales por pais y SLA)

---

## 2. Entidades del sistema de inventario

| Entidad | Significado en TrackFlow |
| --- | --- |
| `Product` | SKU de un cliente (marca), por ejemplo: camiseta talla M de Fashion Co o auricular bluetooth de ElectroBrand. Cada SKU tiene categoria y pertenece a un cliente. |
| `InboundOrder` | Orden de entrada: recepcion de mercancia de un cliente en un almacen (Los Angeles o Zaragoza). |
| `OutboundOrder` | Orden de salida: picking y despacho de pedido hacia transportista para entrega final. |
| `warehouse` | Almacen: `los_angeles` o `zaragoza`. |
| `client` | Marca B2B duena del SKU. |

---

## 3. Metricas obligatorias de telemetria

Estas metricas son obligatorias desde el inicio y deben quedar instrumentadas de punta a punta.

| `event_type` | Se dispara cuando... | Hipotesis de negocio | Decision que habilita |
| --- | --- | --- | --- |
| `inbound_order_created` | Un almacen registra recepcion de mercancia de un cliente. | Necesitamos medir volumen entrante por cliente y almacen. | Planificar capacidad de almacen y personal segun volumen entrante (Ana). |
| `outbound_order_created` | Un almacen completa picking y despacho de un pedido. | Necesitamos medir volumen de pedidos procesados por cliente y almacen y su ritmo. | Detectar cuellos de botella antes de afectar SLA de entrega (Ana). |
| `stock_threshold_triggered` | El stock de un SKU cae por debajo del minimo configurado para ese cliente. | Necesitamos medir frecuencia de quiebres de stock por cliente/SKU. | Alertar a cliente y equipo comercial antes de ruptura de stock (Miguel). |
| `direct_stock_edit_rejected` | Un usuario intenta modificar stock directamente y el sistema lo rechaza. | Necesitamos detectar intentos de saltar trazabilidad operativa. | Reforzar capacitacion o permisos en el almacen con mayor frecuencia de incidentes. |
| `inventory_discrepancy_detected` | Conteo fisico o auditoria detecta diferencia entre stock sistema y stock real. | Necesitamos localizar SKUs y almacenes con mayor discrepancia. | Priorizar auditorias sobre SKUs de mayor tasa de discrepancia (Ana). |

### Campos minimos en `properties`

Ademas del envelope estandar de telemetria, todos los eventos de inventario deben incluir:

- `warehouse` (`los_angeles` o `zaragoza`)
- `client_id`
- `product_id` (SKU)
- `product_category`
- `quantity`

### Regla de privacidad

No incluir datos personales del consumidor final (destinatario del paquete) en `properties`.

Estos eventos describen inventario de almacen, no envios de ultima milla.

---

## 4. Reutilizacion futura de estos datos

Estas metricas no son solo para el reporte tecnico actual.

Se reutilizaran en siguientes fases para:

- automatizaciones operativas
- dashboards de operaciones
- reporting ejecutivo global

Disenar los eventos como un contrato estable para terceros:

- agregable por `warehouse`
- agregable por `client_id`
- agregable por pais
- sin dependencia de conocimiento tacito del implementador

---

## 5. Datos semilla sugeridos

Generar al menos:

- 8 a 10 SKUs
- minimo 2 clientes
- cobertura de 3 categorias: moda, electronica y cosmetica
- ambos almacenes: Los Angeles y Zaragoza
- 15 a 20 ordenes de entrada distribuidas entre ambos almacenes
- 15 a 20 ordenes de salida
- minimo 2 casos de `stock_threshold_triggered`
- minimo 1 caso de `inventory_discrepancy_detected`

---

## 6. Restricciones de negocio

- El stock nunca se modifica directamente: toda modificacion pasa por `InboundOrder` u `OutboundOrder`, trazable a usuario.
- Cada SKU pertenece a un unico cliente: no mezclar inventario entre clientes en el mismo `product_id`.
- Los eventos de inventario no incluyen datos de transportista ni del destinatario final: ese dominio pertenece a ultima milla.

---

## 7. Criterios de implementacion para fases de telemetria

Para considerar esta base correctamente aplicada en fases posteriores:

1. Plan
- El catalogo de eventos incluye los 5 `event_type` obligatorios.
- Cada evento tiene hipotesis, decision y owner de negocio.

2. Captura
- Los eventos se disparan en el punto exacto del flujo funcional.
- Se valida presencia de los campos minimos de `properties`.

3. Almacenamiento
- El backend persiste eventos con versionado de esquema.
- Se registran rechazos por payload invalido sin romper todo el batch.

4. Reporte
- Se calculan agregados por almacen, cliente y pais.
- Se reportan frecuencias de threshold/discrepancia y volumen de entrada/salida.

---

## 8. Checklist rapido de validacion

- [ ] Existen los 5 eventos obligatorios en catalogo.
- [ ] Todos los eventos de inventario incluyen `warehouse`, `client_id`, `product_id`, `product_category`, `quantity`.
- [ ] No hay PII de consumidor final en eventos de inventario.
- [ ] Hay datos semilla suficientes para probar volumen y casos borde.
- [ ] El reporte permite comparativa Los Angeles vs Zaragoza.
- [ ] El reporte permite comparativa por cliente y categoria.
