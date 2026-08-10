# CACHING REPORT

Fecha: 2026-08-10
Alcance: website (Next.js), backoffice (Next.js), incidents-api (FastAPI)

## 1) Decisiones en el frontend

### 1.1 Carga diferida (lazy loading)

#### Componente: LandingInteractions (landing /)
- Decision: carga diferida con `next/dynamic`.
- Motivo: concentra logica de scroll, observers, animaciones y carrusel; no bloquea el primer render de contenido principal.
- Beneficio estimado: menor JS inicial e hidratacion mas ligera en la landing, especialmente en dispositivos medios.

#### Componente: QuoteForm (ruta /application)
- Decision: carga diferida con `next/dynamic` + fallback visual "Cargando formulario...".
- Motivo: formulario cliente con validaciones, estados y handlers; no es necesario para mostrar cabecera y contexto inicial.
- Beneficio estimado: mejora el tiempo de pintado inicial de la ruta y difiere trabajo de JS hasta intencion de uso.

### 1.2 Memoizacion en frontend

#### Componente: IncidentsManagementPanel (backoffice)
- Decision: memoizacion de `incidentRows` (derivacion no trivial) y del `dateTimeFormatter`.
- Motivo: se evitaba recalculo por fila en cada render (`includes`, opciones por estado y formato de fecha).
- Cambio aplicado:
  - `incidentRows` se construye con `useMemo` usando `Set` para lookups O(1).
  - `formattedUpdatedAt` queda precomputado por fila.
- Dependencias: `incidents`, `updatingIds`, `dateTimeFormatter`.
- Beneficio estimado: menor coste de render en tablas de incidencias grandes y menos trabajo repetido en re-renders.

## 2) Decisiones en el backend

### Endpoint cacheado: GET /suppliers
- Coste de operacion: medio-alto.
  - Lee todos los proveedores y filtra en memoria por `country` y `category`.
- Frecuencia estimada de llamadas: alta.
  - Se consulta al abrir panel y al cambiar filtros.
- TTL elegido: 45 segundos.
- Estrategia de cache:
  - Cache en memoria por clave de query (`country`, `category`).
- Estrategia de invalidacion:
  - Limpieza total de cache de suppliers en:
    - POST /suppliers
    - PATCH /suppliers/{supplier_id}/rate
    - PATCH /suppliers/{supplier_id}/status
    - DELETE /suppliers/{supplier_id}

### Endpoint cacheado: GET /auth/me
- Coste de operacion: medio.
  - Decodifica token y carga usuario + perfil.
- Frecuencia estimada de llamadas: alta.
  - Carga de sesion inicial, recargas y refrescos de estado auth.
- TTL elegido: 20 segundos.
- Estrategia de cache:
  - Cache en memoria por token bearer.
  - Indices auxiliares token->user y user->tokens para invalidar por usuario.
- Estrategia de invalidacion:
  - Invalida todas las entradas del usuario en:
    - PUT /profiles/me
    - PUT /users/{user_id}
    - DELETE /users/{user_id}
    - POST /auth/change-password
    - POST /auth/reset-password

## 3) Intercambios reconocidos (frescura vs rendimiento)

### Caso A: GET /suppliers (TTL 45s)
- Trade-off: se acepta una posible desactualizacion breve (hasta 45s) para reducir lecturas completas y filtros repetidos.
- Justificacion: cambios de proveedores (alta/baja/ajuste) no suelen ocurrir en cadencia de segundos; la invalidacion por escrituras cubre casos criticos.

### Caso B: GET /auth/me (TTL 20s)
- Trade-off: se acepta una ventana muy corta de potencial stale por token para bajar coste de validaciones repetidas.
- Justificacion: perfil/rol rara vez cambia continuamente; ademas, cualquier mutacion relevante invalida cache por usuario.

## 4) Que no se cacheo y por que

### No cacheado: GET /inventory/products
- Coste/frecuencia: alto/alto (buen candidato por rendimiento puro).
- Motivo de exclusion inicial: baja estabilidad relativa del dato (stock cambia con entradas/salidas), por lo que un TTL corto puede exponer stock desactualizado en flujo operativo.
- Decision: priorizar primero endpoints con mejor equilibrio coste + frecuencia + estabilidad (suppliers y auth/me).

### No cacheado: GET /api/incidents/summary
- Coste/frecuencia: medio-alto/alto.
- Motivo de exclusion inicial: la vista de incidencias busca feedback operativo cercano a tiempo real; con cambios de estado frecuentes, el stale afecta mas al usuario.
- Decision: pospuesto hasta tener telemetria de latencia y una estrategia de invalidacion granular por eventos.

## 5) Resultado operativo

- Se introdujo cache TTL en memoria con locks para concurrencia segura.
- Se implemento invalidacion por operaciones de escritura para evitar obsolescencia prolongada.
- Se aplico carga diferida y memoizacion no trivial en frontend para reducir coste de JS y render.
