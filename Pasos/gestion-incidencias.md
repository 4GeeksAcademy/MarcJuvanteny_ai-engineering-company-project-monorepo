# Gestor de Incidencias Centralizado — Especificación

Especificación funcional para el modelo de datos, el seed histórico, el backend y el frontend del Gestor de Incidencias Centralizado (Hito 10).

> ⚠️ Nota de origen de los datos: el `CONTEXT.es.md` del repositorio corresponde al **Hito 09** (Directorio de Proveedores de TrackFlow), no a este proyecto. Las categorías y sedes de abajo provienen del resumen en [memory-bank/progress.md](../memory-bank/progress.md) (Hito 10). Solo 3 de las 9 categorías están confirmadas ahí — faltan 6 por definir en un CONTEXT completo de Hito 10 que todavía no existe en el repositorio.

## Modelo de datos

- [ ] Define el modelo `Incident` con los siguientes campos:
  - `id` — identificador único generado automáticamente.
  - `title` — título breve de la incidencia (obligatorio).
  - `description` — descripción detallada (obligatorio).
  - `category` — categoría de la incidencia. 9 categorías válidas en total; confirmadas hasta ahora: `lost_parcel`, `carrier_issue`, `inventory_discrepancy` (**faltan 6 por definir**).
  - `status` — estado del ciclo de vida: `open`, `in_progress`, `resolved`, `discarded`.
  - `origin` — origen del reporte: `customer`, `branch`, `internal`.
  - `branch` — sede que gestiona o reporta la incidencia (obligatorio para todos los orígenes). Sedes válidas: `la_warehouse`, `la_office`, `zaragoza_warehouse`, `zaragoza_office`, `central` (usar `"central"` cuando no corresponda a una sede específica).
  - `created_at` — fecha y hora de creación, generada automáticamente.
  - `updated_at` — fecha y hora de última modificación, actualizada automáticamente.
- [ ] Aplica las restricciones de integridad necesarias: campos obligatorios, valores permitidos en `status`, `origin`, `category` y `branch`.

## Seed de datos históricos (`/scripts`)

- [ ] Crea el script `seed_incidents.py` que lee el fichero CSV del proyecto anterior y carga todas sus filas en la base de datos asignando `origin: "customer"` a todos los registros.
- [ ] El script debe reutilizar la lógica de validación ya existente — extrae las funciones comunes a `packages/shared/` si aún no lo has hecho: los registros inválidos del CSV no se insertan y se reportan en consola al final de la ejecución.
- [ ] El script es idempotente: se ejecuta varias veces y no duplica registros (comprueba por un campo identificador del CSV antes de insertar).

## Backend (`/services`)

### Endpoints de gestión

- [ ] `POST /api/incidents` — crea una nueva incidencia. Valida todos los campos obligatorios y devuelve `400` con un mensaje descriptivo si falta alguno o contiene un valor no permitido.
- [ ] `GET /api/incidents` — devuelve la lista de incidencias. Acepta parámetros de filtro opcionales: `status`, `origin`, `branch`, `category`.
- [ ] `GET /api/incidents/{id}` — devuelve el detalle de una incidencia. Devuelve `404` si no existe.
- [ ] `PATCH /api/incidents/{id}/status` — actualiza únicamente el estado de una incidencia. Valida que la transición sea coherente con el ciclo de vida: desde `open` se puede avanzar a `in_progress` o `discarded`; desde `in_progress` se puede avanzar a `resolved` o `discarded`; los estados `resolved` y `discarded` son finales.
- [ ] `GET /api/incidents/summary` — devuelve las métricas agregadas: total por estado, total por categoría, total por origen y total por sede.

### Manejo de errores en el backend

- [ ] Toda excepción no controlada devuelve `500` con un mensaje genérico — nunca el stack trace completo.
- [ ] Los errores de validación devuelven `400` con un objeto JSON que identifica el campo problemático y describe el error en lenguaje claro.
- [ ] Los endpoints de lectura no fallan si la base de datos está vacía: devuelven lista vacía o métricas en cero.

## Frontend (`/uis`)

### Formulario de registro

- [ ] Crea una página de registro de incidencias accesible desde el menú de la aplicación.
- [ ] El formulario incluye todos los campos del modelo. El campo `branch` es siempre visible y obligatorio, con las opciones `la_warehouse`, `la_office`, `zaragoza_warehouse`, `zaragoza_office` y `central`.
- [ ] Cuando `origin` sea `branch`, el campo `branch` se destaca visualmente para recordar al usuario que está reportando desde una sede específica.
- [ ] Al enviar, el formulario muestra un indicador de carga mientras la petición está en curso — el botón de envío queda deshabilitado durante ese tiempo.
- [ ] Si la API devuelve un error, el formulario muestra un mensaje comprensible para el usuario, nunca el mensaje técnico del servidor. Si el error identifica un campo concreto, el mensaje aparece junto a ese campo.
- [ ] Tras un envío exitoso, el formulario se limpia y muestra una confirmación clara.

### Panel de incidencias

- [ ] Crea una página de listado con todas las incidencias registradas, con filtros por `status`, `origin` y `branch`.
- [ ] Muestra un indicador de carga mientras se obtienen los datos.
- [ ] Si la petición falla, muestra un mensaje de error con opción de reintentar — la página no queda en blanco ni rota.
- [ ] Si no hay incidencias que mostrar (lista vacía o sin resultados para los filtros aplicados), muestra un mensaje informativo — nunca una tabla vacía sin contexto.
- [ ] Cada incidencia permite actualizar su estado directamente desde el listado. Si la actualización falla, el estado visual vuelve al valor anterior y se notifica al usuario.

### Panel de resumen

- [ ] Muestra las métricas agregadas del endpoint `/summary`: totales por estado, por categoría, por origen y por sede.
- [ ] Si los datos tardan en cargarse o fallan, el panel muestra el estado correspondiente sin romper el resto de la página.

---

⚠️ **IMPORTANTE:** Los nombres de campos, categorías, sedes y valores de tu implementación deben coincidir exactamente con lo especificado en el CONTEXT real de Hito 10. Una implementación genérica que ignore el contexto no será aceptada. Antes de implementar, completa las 6 categorías restantes que aún no están confirmadas en el repositorio (ver nota al inicio de este documento).
