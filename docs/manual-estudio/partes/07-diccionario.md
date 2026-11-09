
---

<a id="s17"></a>
## 17. Diccionario de tecnicismos

Organizado por categorías y, dentro de cada una, por orden alfabético. **Dónde** indica el archivo o paso de TrackFlow en el que aparece.

### 17.1 Programación general

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| **async / await** | Forma de escribir código que puede "esperar" (a la red, a un disco) sin bloquear todo lo demás | Poner la lavadora y, mientras, hacer la cena | Endpoints SSE y WebSocket, nodos async del agente |
| **Backoff exponencial** | Esperar cada vez más entre reintentos (2 s, 4 s, 8 s…) | Si nadie contesta al timbre, esperas un poco más antes de volver a llamar | Celery (paso 22), Prefect (paso 20), reconexión SSE/WS |
| <a id="g-capa"></a>**Capa de integración** | Módulo que concentra todas las llamadas a un servicio externo | Una sola ventanilla en vez de ir a cada despacho | `lib/inventory.ts` (paso 4) |
| **Clase / objeto** | Plantilla (clase) para crear "cosas" con datos y comportamiento (objetos) | El molde (clase) y las galletas (objetos) | `RFPTicket`, `ChatManager`, `SlidingWindowRateLimiter` |
| **Concurrencia** | Varias cosas ocurriendo a la vez y compitiendo por los mismos recursos | Dos personas queriendo el mismo baño | Caché con `RLock` (paso 13), bloqueo de jobs (paso 21) |
| **Dependencia (librería)** | Código de otros que tu proyecto usa | Ingredientes comprados en vez de cultivarlos | `pyproject.toml`, `package.json` |
| **Determinista** | Que con la misma entrada siempre da la misma salida | Una calculadora (no una tirada de dados) | Clasificadores y evaluadores del paso 29-30 |
| **Docstring** | Texto de documentación dentro del código de una función | La etiqueta de instrucciones pegada a un aparato | Casi todos los módulos Python del proyecto |
| **Enum** | Lista cerrada de valores permitidos | Las opciones de un menú: no puedes pedir algo que no está | `IncidentStatus`, `TicketStatus` |
| **Expresión regular (regex)** | Patrón de texto para buscar o validar | Un molde para detectar formas de palabras | Guardrails, extractor de pedidos, clasificador de RFP |
| **Fake / mock / doble de prueba** | Pieza falsa que sustituye a una real en los tests | Un maniquí en un simulacro de incendio | `SpyLLM`, `FakeLLM`, embeddings léxicos |
| **Función** | Bloque de código con nombre que recibe datos y devuelve un resultado | Una receta | `_compute_current_stock`, `retrieve` |
| **Función pura** | Función que no cambia nada fuera de ella y siempre da lo mismo con las mismas entradas | Una fórmula matemática | Transformaciones del pipeline (paso 20), métricas (paso 17) |
| **Heurística** | Regla práctica, no "inteligente", que funciona en la mayoría de casos | "Si huele a quemado, mira el horno" | `classify_intent`, propuesta de memoria |
| <a id="g-idempotencia"></a>**Idempotencia** | Hacer algo dos veces deja el mismo resultado que hacerlo una | Pulsar el botón del ascensor 5 veces: sigue viniendo una vez | Seed (paso 2), indexación RAG, pipeline KPIs, job nocturno |
| **Inyección de dependencias** | Pasar a una función las piezas que necesita en vez de que las cree ella | Darle al cocinero los ingredientes en vez de que vaya a comprar | `embed_fn`, `generate_fn`, `agent_fn` inyectables en tests |
| <a id="g-lock"></a>**Lock (bloqueo)** | Mecanismo que impide que dos procesos hagan lo mismo a la vez | El pestillo del baño | `RLock` de caché; índice único parcial de `ops.job_runs` |
| <a id="g-maquina-estados"></a>**Máquina de estados** | Conjunto de estados y de transiciones permitidas entre ellos | Un semáforo | Incidencias (paso 2), tickets de RFP (pasos 29-31) |
| **Monorepo** | Un solo repositorio con muchos proyectos dentro | Un edificio con varias empresas | Todo TrackFlow |
| **O(1), O(n)** | Forma de decir cuánto crece el trabajo con el tamaño de los datos | O(1): mirar un número de taquilla; O(n): leer toda la lista | `useMemo` con `Set` (paso 9), análisis CSV (paso 12) |
| **Refactorizar** | Reorganizar código sin cambiar lo que hace | Ordenar el armario sin tirar ropa | `useApiSubmit` (paso 18) |
| <a id="g-stacktrace"></a>**Stack trace** | Lista detallada de dónde falló el programa | La caja negra de un avión | Nunca se envía al cliente (paso 3) |
| <a id="g-stderr"></a>**stderr / stdout** | Las dos "salidas" de un programa: la normal (stdout) y la de errores (stderr) | Dos bandejas: correo normal y reclamaciones | Scripts (paso 3), cron (paso 21) |
| **Test unitario / de integración** | Prueba de una pieza aislada / de varias piezas juntas | Probar el motor / probar el coche entero | `tests/`, ~270 funciones de test |
| <a id="g-trycatch"></a>**try / catch (except)** | Bloque que "intenta" algo y captura el error si falla | Una red bajo un trapecista | Todo el frontend (paso 3) y el backend |
| **Tipado / TypeScript** | Declarar qué tipo de dato es cada cosa, para detectar errores antes de ejecutar | Etiquetar cada caja de una mudanza | `uis/` |
| <a id="g-env"></a>**Variable de entorno** | Valor de configuración que se lee del sistema, no del código | Las instrucciones pegadas en la nevera, no grabadas en la nevera | `.env`, `JWT_SECRET_KEY`, `GENERATION_API_KEY` |

### 17.2 Web y frontend

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| **Backoffice** | Aplicación interna para el personal | La trastienda de una tienda | `uis/backoffice` |
| **Componente** | Pieza reutilizable de una interfaz | Una pieza de LEGO | `components/*.tsx` |
| **Core Web Vitals (LCP, CLS, INP)** | Métricas de Google de velocidad (LCP), estabilidad visual (CLS) y respuesta a clics (INP) | Lo rápido que se sirve el plato, que no se mueva la mesa y lo rápido que te atiende el camarero | Auditoría web (paso 18) |
| <a id="g-cors"></a>**CORS** | Regla del navegador que decide qué webs pueden llamar a una API de otro dominio | El portero que mira la lista de invitados | `CORSMiddleware` en `main.py` |
| **fetch** | Función del navegador para hacer peticiones HTTP | Mandar un mensajero | `authFetch`, `use-rfp-ticket-stream.ts` |
| <a id="g-guard"></a>**Guard (de rutas)** | Componente que impide ver una página sin permiso | El torno de entrada del metro | `auth-guard.tsx` (paso 7) |
| **Hidratación** | Momento en el que el HTML que llegó del servidor "cobra vida" con JavaScript | Una maqueta que de repente funciona | Lazy loading (paso 11) |
| <a id="g-hook"></a>**Hook (React)** | Función especial de React para reutilizar lógica con estado | Un accesorio que acoplas a cualquier aparato | `useApiSubmit`, `useCxChat`, `useRfpTicketStream` |
| <a id="g-lazy"></a>**Lazy loading** | Cargar una parte de la página solo cuando hace falta | No sacar el postre hasta terminar el segundo plato | `next/dynamic` en la web (paso 11) |
| <a id="g-lighthouse"></a>**Lighthouse** | Herramienta de Google que puntúa rendimiento, accesibilidad y SEO de una web | La ITV de una página web | Paso 18 (sin medición real) |
| **localStorage** | Pequeño almacén de datos en el navegador | Un cajón en tu escritorio | Guarda el JWT y el `session_id` del chat |
| <a id="g-nextjs"></a>**Next.js** | Framework sobre React con rutas por carpetas y renderizado en servidor | Un kit de cocina con los utensilios ya colocados | Backoffice y web |
| **React** | Librería para construir interfaces con componentes | Piezas de LEGO para pantallas | `uis/` |
| <a id="g-render"></a>**Renderizar** | Calcular y pintar lo que se ve en pantalla | Dibujar el fotograma de una película | Paso 9 |
| **SEO** | Optimización para buscadores (Google) | Poner bien el cartel de la tienda para que te encuentren | Web corporativa, JSON-LD |
| **Tailwind CSS** | Estilos con clases cortas ya hechas (`p-4`, `text-red-500`) | Ropa de tallas estándar en lugar de a medida | `uis/website` |
| <a id="g-usememo"></a>**useMemo** | Hook que guarda un cálculo y solo lo repite si cambian sus datos | Apuntar la cuenta en un papel en vez de recalcularla | Panel de incidencias (paso 9) |

### 17.3 Backend, APIs y comunicación

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| **API** | Conjunto de "puertas" por las que un programa pide cosas a otro | La carta de un restaurante: lo que se puede pedir | `incidents-api`, `knowledge-api` |
| **ASGI / Uvicorn** | Estándar y servidor que ejecutan aplicaciones web asíncronas en Python | El camarero que lleva las peticiones a la cocina (FastAPI) | Arranque de todos los servicios |
| <a id="g-broker"></a>**Broker** | Intermediario donde se dejan los mensajes de la cola | La oficina de correos | Redis para Celery |
| **Código de estado HTTP** | Número que resume el resultado: 200 bien, 201 creado, 202 aceptado, 400 mal pedido, 401 sin identificar, 403 sin permiso, 404 no existe, 409 conflicto, 422 datos inválidos, 428 falta confirmación, 429 demasiadas peticiones, 500 error del servidor, 502 fallo de un servicio externo | Las caras de un semáforo, con más colores | Todos los endpoints |
| <a id="g-celery"></a>**Celery** | Sistema para ejecutar tareas en segundo plano | Una cocina trasera que prepara los pedidos largos | `celery_app.py`, `tasks.py`, `rfp_tasks.py` |
| <a id="g-cola"></a>**Cola de tareas** | Lista de trabajos pendientes que procesan los workers por orden | La fila del supermercado | Celery + Redis (paso 22) |
| <a id="g-dlq"></a>**DLQ (Dead Letter Queue)** | Lugar donde van las tareas que fallaron definitivamente, para revisarlas | La oficina de cartas sin destinatario | `task_dlq.py` (paso 22) |
| <a id="g-endpoint"></a>**Endpoint** | Una dirección concreta de la API (método + ruta) | Una ventanilla concreta del ayuntamiento | `POST /rfp/tickets`, `GET /inventory/orders` |
| <a id="g-fastapi"></a>**FastAPI** | Framework de Python para crear APIs rápidas y con validación automática | Un kit de montaje de ventanillas | Todos los servicios |
| **Flower** | Panel web para ver las tareas de Celery | El tablón de pedidos de la cocina | `docker-compose.yml` (paso 22) |
| <a id="g-http"></a>**HTTP / HTTPS** | El protocolo de la web: petición y respuesta (HTTPS es la versión cifrada) | Pedir en la barra (con sobre cerrado, en el caso de HTTPS) | Toda la comunicación |
| <a id="g-json"></a>**JSON** | Formato de texto para datos estructurados (`{"clave": "valor"}`) | Un formulario con casillas etiquetadas | Todas las APIs |
| <a id="g-jsonrpc"></a>**JSON-RPC** | Forma de llamar funciones remotas enviando JSON | Rellenar un impreso de "solicito que se ejecute X" | Protocolo MCP |
| **Keep-alive** | Mensaje vacío periódico para que la conexión no se cierre | Decir "sigo aquí" en una llamada en silencio | SSE cada 15 s (paso 32) |
| **Last-Event-ID** | Número del último evento recibido, para pedir solo lo que falta al reconectar | El marcapáginas de un libro | SSE (paso 32) |
| **Middleware** | Código que se ejecuta antes o después de cada petición | El control de seguridad del aeropuerto | CORS, autenticación del MCP |
| <a id="g-outbox"></a>**Outbox** | Tabla donde se apuntan eventos en la misma transacción que los datos, para enviarlos después | Un buzón de salida que se vacía con regularidad | `rfp_ticket_events` (paso 32) |
| <a id="g-pubsub"></a>**Pub/Sub** | Patrón donde unos "publican" mensajes en un canal y otros "se suscriben" a él | Una emisora de radio y sus oyentes | `chat_pubsub.py` (paso 33) |
| **Pydantic** | Librería que valida datos según su tipo | Un revisor de formularios | Modelos de todos los servicios |
| **REST** | Estilo de API basado en recursos y métodos (GET, POST, PATCH, DELETE) | Verbos sobre sustantivos: "leer pedido", "crear pedido" | Todos los servicios |
| <a id="g-sse"></a>**SSE (Server-Sent Events)** | El servidor envía mensajes al navegador por una conexión abierta, en un solo sentido | La pantalla de turnos de una farmacia | `GET /rfp/events` (paso 32) |
| <a id="g-streaming"></a>**Streaming** | Enviar la respuesta poco a poco, a medida que se genera | Ver un vídeo mientras se descarga | Chat token a token (paso 33) |
| <a id="g-websocket"></a>**WebSocket** | Conexión abierta en la que cliente y servidor hablan en los dos sentidos | Una llamada de teléfono | `WS /chat/ws` (paso 33) |
| <a id="g-worker"></a>**Worker** | Proceso que toma tareas de la cola y las ejecuta | El cocinero de la cocina trasera | Servicio `worker` del compose |

### 17.4 Bases de datos

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| <a id="g-pk"></a>**Clave primaria (PK)** | Columna que identifica cada fila de forma única | El DNI | `event_id` de `telemetry_events` |
| **Clave natural** | Identificador con significado de negocio | "Semana 35 + almacén ZGZ + marca X" | `(iso_week, warehouse, client_id)` (paso 20) |
| <a id="g-gin"></a>**GIN (índice)** | Índice especial de PostgreSQL para buscar dentro de JSON | El índice temático de un libro | `properties` de telemetría (paso 16) |
| <a id="g-indice"></a>**Índice** | Estructura que acelera las búsquedas en una tabla | El índice alfabético de un libro | `timestamp`, `event_type`, `(job_name, target_date)` |
| <a id="g-jsonb"></a>**JSONB** | Columna de PostgreSQL que guarda JSON de forma eficiente | Una caja con compartimentos flexibles | `properties`, `key_aspects`, `payload` |
| **ORM** | Librería que convierte tablas en clases del lenguaje | Un traductor entre Python y SQL | SQLModel / SQLAlchemy |
| **PostgreSQL / Supabase** | Base de datos relacional (Supabase es PostgreSQL gestionado en la nube) | Un archivador muy ordenado y fiable | Inventario, telemetría, RFP, reporting |
| **Qdrant** | Base de datos de vectores | Una biblioteca ordenada por temas, no por título | Colección `trackflow_knowledge` |
| **Redis** | Base de datos en memoria, muy rápida | Una pizarra junto a la puerta | Cola de Celery, memoria del agente |
| **Schema (esquema)** | Estructura de una tabla, o espacio de nombres en PostgreSQL | El plano de un archivador | `reporting.*`, `ops.*` |
| <a id="g-seed"></a>**Seed (sembrar)** | Cargar datos iniciales en una base | Llenar la nevera antes de abrir el restaurante | `scripts/seed_incidents.py`, `seed_inventory_if_empty` |
| <a id="g-sku"></a>**SKU** | Código único de un producto en inventario | La matrícula de un producto | `CLT-SNK-W-42-Z` |
| **SQL** | Lenguaje para consultar bases de datos relacionales | Preguntas formales al archivador | Consultas generadas por SQLModel |
| **Staging (tabla)** | Tabla intermedia donde se prepara la carga antes de pasarla a la definitiva | La mesa donde emplatas antes de servir | `reporting._stg_exec_weekly_inventory_kpis` |
| **TinyDB** | Base de datos minimalista guardada en un archivo JSON | Una libreta en vez de un archivador | `suppliers.json` |
| **Transacción** | Grupo de operaciones que se hacen todas o ninguna | Una transferencia bancaria: o sale y entra el dinero, o no pasa nada | UPSERT del pipeline, outbox SSE |
| <a id="g-upsert"></a>**UPSERT** | Insertar una fila, o actualizarla si ya existe | Apuntarse a una lista: si ya estás, solo se corrige tu teléfono | `ON CONFLICT … DO UPDATE` (paso 20) |
| <a id="g-vectordb"></a>**Base de datos vectorial** | Base de datos que busca por parecido de significado (vectores), no por palabras exactas | Un librero que te trae "libros parecidos a este" | Qdrant |

### 17.5 Datos y machine learning

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| **DataFrame / pandas** | Tabla de datos en Python (pandas es la librería) | Una hoja de cálculo programable | Telemetría, KPIs, ventas |
| <a id="g-escalado"></a>**Escalado (StandardScaler)** | Poner las variables en una escala comparable | Pasar euros y dólares a la misma moneda | `scale_features()` (paso 23) |
| <a id="g-etl"></a>**ETL** | Extraer, Transformar y Cargar datos | Recoger verduras, cocinarlas y servirlas | Pipeline de KPIs (pasos 19-20) |
| **Feature (variable)** | Dato de entrada del modelo | Los ingredientes de una receta | Mes, seno/coseno, *lags* |
| <a id="g-leakage"></a>**Fuga de datos (data leakage)** | Que el modelo vea, al entrenar, información del futuro o de la prueba | Estudiar con el examen ya resuelto | Split temporal y *lags* (pasos 23-24) |
| <a id="g-gini"></a>**Gini (normalizado)** | Mide si el modelo **ordena** bien de mayor a menor | Acertar quién es más alto aunque falles la altura exacta | 0,935 (paso 24) |
| **Hiperparámetro** | Ajuste del modelo que se fija antes de entrenar | La temperatura del horno | `max_depth=6`, `min_samples_leaf=2` |
| <a id="g-kpi"></a>**KPI** | Indicador clave de rendimiento | El marcador de un partido | `fulfillment_rate`, tiempo de ciclo |
| <a id="g-lag"></a>**Lag / media móvil** | Valor de meses anteriores / promedio de los últimos meses | Recordar cuánto vendiste el mes pasado | `lag_1`, `lag_12`, `rolling_mean_3` (paso 24) |
| **MAE** | Error medio absoluto | Cuántos euros me equivoco de media | Paso 24 |
| <a id="g-ml"></a>**Machine learning** | Programas que aprenden patrones a partir de datos | Aprender a reconocer perros viendo muchas fotos | Modelo de ventas |
| <a id="g-mse"></a>**MSE / RMSE** | Error cuadrático medio / su raíz (castiga más los errores grandes) | Un profesor que penaliza más los suspensos graves | RMSE 3 % (paso 24) |
| <a id="g-overfitting"></a>**Sobreajuste (overfitting)** | El modelo memoriza el entrenamiento y generaliza peor | Aprenderse las respuestas del examen de prueba de memoria | Diagnóstico del paso 24 |
| <a id="g-percentil"></a>**Percentil (p95)** | Valor por debajo del cual está el 95 % de los datos | "El 95 % de las peticiones tarda menos de X" | Latencia (paso 17) |
| <a id="g-psi"></a>**PSI** | Mide cuánto ha cambiado la distribución de una variable entre dos periodos | Comprobar si los clientes de este año se parecen a los del pasado | 0,05 (paso 24) |
| <a id="g-r2"></a>**R²** | Proporción de la variación que el modelo explica (1 = perfecto) | Qué parte del misterio resuelve el detective | 0,948 (paso 24) |
| <a id="g-rf"></a>**Random Forest** | Muchos árboles de decisión que votan juntos | Preguntar a 300 expertos y promediar | `RandomForestRegressor` (paso 23) |
| <a id="g-regresion"></a>**Regresión** | Predecir un número (no una categoría) | Estimar el precio de un piso | Ingreso mensual |
| **Target (objetivo)** | Lo que el modelo intenta predecir | La pregunta del examen | `revenue_eur` |
| <a id="g-split"></a>**Train / test split** | Separar datos para entrenar y datos para evaluar | Estudiar con unos ejercicios y examinarse con otros | 2016-2023 / 2024-2025 |
| <a id="g-tscv"></a>**TimeSeriesSplit** | Validación cruzada que respeta el orden del tiempo | Examinarte siempre de temas posteriores a los estudiados | Paso 24 |
| <a id="g-cv"></a>**Validación cruzada** | Evaluar el modelo varias veces con distintas particiones | Hacer varios exámenes de prueba distintos | 5 *folds* (paso 24) |

### 17.6 IA generativa y RAG

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| **Alucinación** | Cuando un LLM inventa datos con total seguridad | Un estudiante que se inventa la respuesta con aplomo | Se mitiga con RAG y `no_context` |
| <a id="g-chunk"></a>**Chunking (trocear)** | Dividir documentos en fragmentos para buscarlos | Cortar un libro en fichas | Por encabezado `##` (paso 25) |
| <a id="g-embedding"></a>**Embedding** | Lista de números que representa el significado de un texto | Las coordenadas de una idea en un mapa | `embed()` (paso 25) |
| **Faithfulness** | Que la respuesta sea fiel al contexto, sin inventar | Un periodista que solo cuenta lo que dicen sus fuentes | No medida (sin LLM real) |
| **Flesch (legibilidad)** | Fórmula que puntúa lo fácil que es leer un texto | Un medidor de "texto de periódico" frente a "texto de notario" | Evaluador de RFP (paso 30) |
| <a id="g-llm"></a>**LLM** | Modelo de lenguaje grande, que genera texto | Un autocompletado extremadamente potente | `GENERATION_MODEL` |
| **MarkItDown** | Conversor de documentos (PDF) a Markdown | Un escáner que pasa el papel a texto | `pdf_conversion.py` (paso 29) |
| <a id="g-prompt"></a>**Prompt** | El texto que se le da al LLM para que responda | La pregunta del examen, con sus instrucciones | `_build_prompt` |
| <a id="g-rag"></a>**RAG** | Recuperar documentos relevantes y dárselos al LLM antes de responder | Examen con libro abierto | `data/process` y `data/pipelines/rag.py` |
| <a id="g-recall"></a>**Recall@k** | Porcentaje de preguntas en las que el fragmento correcto aparece entre los k primeros | "¿Estaba el libro correcto entre los 3 que te trajo el bibliotecario?" | 80 % con k=3 (paso 25) |
| <a id="g-coseno"></a>**Similitud coseno** | Medida de lo parecidos que son dos vectores (de −1 a 1) | Lo alineadas que apuntan dos flechas | Búsqueda en Qdrant, `min_score` |
| <a id="g-system-prompt"></a>**System prompt** | Instrucciones fijas que definen el rol y las reglas del LLM | El reglamento interno de un empleado | `AGENT_SYSTEM_PROMPT` |
| **Token (de LLM)** | Trozo de palabra con el que trabaja el LLM | Las sílabas de una frase | `token_chunk` del chat |

### 17.7 Agentes, MCP y orquestación

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| <a id="g-agente"></a>**Agente** | Programa que decide pasos y usa herramientas para cumplir un objetivo | Un empleado con una tarea y acceso a ciertas aplicaciones | Agente CX, agentes de RFP |
| **AGENTS.md / memory-bank** | Documentos que dan reglas y contexto a la IA que programa | El dosier de bienvenida de un empleado nuevo | Raíz del repo |
| **Arbitraje** | Resolver conflictos entre partes con una regla fija | Un árbitro de fútbol | `arbitration.py` (paso 31) |
| <a id="g-checkpoint"></a>**Checkpoint / checkpointer** | Foto del estado del grafo guardada para retomarlo después | Guardar la partida de un videojuego | `MemorySaver`, `PostgresSaver` |
| **Command(resume=…)** | Orden de LangGraph para continuar un grafo pausado con una respuesta | Pulsar "continuar" tras guardar la partida | Aprobación de RFP (paso 31) |
| **Fan-out** | Lanzar varias ramas en paralelo desde un punto | Repartir los platos a varios camareros a la vez | Workers y evaluadores de RFP |
| <a id="g-fastmcp"></a>**FastMCP** | Librería Python para construir servidores MCP | Un kit para montar enchufes estándar | `mcps/trackflow-mcp/server.py` |
| <a id="g-hitl"></a>**Human-in-the-loop** | Una persona aprueba o corrige dentro del flujo automático | El jefe que firma antes de enviar | RFP (`interrupt`), memoria del agente |
| <a id="g-interrupt"></a>**interrupt()** | Función de LangGraph que pausa el grafo hasta recibir una respuesta | Un semáforo en rojo hasta que pase el guardia | `approval_graph.py` |
| <a id="g-langgraph"></a>**LangGraph (grafo, nodo, arista, estado)** | Framework para describir agentes como un grafo: nodos (pasos), aristas (caminos, a veces condicionales) y un estado compartido | Un diagrama de flujo que se ejecuta | `agent_graph.py`, `rfp_intake/*_graph.py` |
| <a id="g-mcp"></a>**MCP (Model Context Protocol)** | Protocolo estándar para que agentes descubran y usen herramientas | Un enchufe universal | `trackflow-mcp` (paso 26) |
| <a id="g-memoria"></a>**Memoria de agente** | Hechos que el agente recuerda entre conversaciones | Las notas de un empleado veterano | Redis, `agent_memory:*` (paso 27) |
| **Multiagente** | Varios agentes especializados colaborando | Un equipo con roles: recepción, especialistas, coordinador | RFP (pasos 29-31) |
| <a id="g-orchestrator"></a>**Orchestrator-worker-synthesizer** | Patrón: uno reparte, varios trabajan y otro resume | Jefe de obra, oficiales y quien redacta el informe | `graph.py` de RFP |
| <a id="g-prefect"></a>**Prefect (flow, task)** | Orquestador de pipelines: un *flow* agrupa *tasks* con reintentos y estados | Un director de orquesta con su partitura | Pipeline de KPIs (paso 20) |
| <a id="g-rfp"></a>**RFP** | *Request for Proposal*: petición formal de propuesta de un cliente | Una licitación | `rfp_intake`, `rfp-requests/` |
| **Skill** | Paquete de instrucciones reutilizable para un agente | Un manual de procedimiento | `.agents/Verificaciondecontratos.md` |
| <a id="g-tool"></a>**Tool (herramienta)** | Función concreta que un agente puede invocar | Una aplicación del ordenador del empleado | 5 tools del MCP |
| <a id="g-traza"></a>**Traza (trace)** | Registro de los pasos que siguió una ejecución | El historial de un GPS | `agent-traces/`, registro de decisiones, `RFPNodeTrace` |
| **Workflow** | Secuencia orquestada de pasos disparada por evento u horario | Una cadena de montaje | cron + Prefect + Celery |

### 17.8 Despliegue, infraestructura y herramientas

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| **Branch / commit / git** | Git guarda el historial; un *commit* es una foto; una *branch* es una línea de trabajo paralela | Versiones guardadas de un documento | Rama `feature/sales-forecast-model` |
| <a id="g-cache"></a>**Caché** | Copia temporal de un resultado para no recalcularlo | Tener el café ya hecho en el termo | `/suppliers`, `/auth/me` (paso 13); transformación en Prefect |
| **CI (integración continua)** | Ejecutar tests automáticamente en cada cambio | Un control de calidad en la cinta | No existe aún (recomendado) |
| <a id="g-contenedor"></a>**Contenedor (Docker)** | Paquete aislado con una app y todo lo que necesita | Un contenedor de barco estándar | `docker-compose.yml` |
| <a id="g-cron"></a>**Cron** | Programador de tareas por horario en Linux | Una alarma diaria | `infra/nightly_export.cron` (02:00) |
| **Docker Compose** | Archivo que levanta varios contenedores juntos | La partitura de una orquesta de contenedores | 8 servicios |
| <a id="g-imagen"></a>**Imagen (Docker)** | La plantilla a partir de la que se crea un contenedor | El molde de un pastel | `uis/Dockerfile`, `services/Dockerfile` |
| **Lint / ESLint / tsc** | Revisores automáticos de estilo y tipos | Un corrector ortográfico | `npm run lint`, `npx tsc` |
| **Loopback (127.0.0.1)** | Dirección que solo es accesible desde la propia máquina | Un intercomunicador interno, sin salida a la calle | Redis, Flower y Qdrant (paso 34) |
| <a id="g-makefile"></a>**Makefile** | Archivo con atajos de comandos | Botones de marcación rápida | `make up`, `make health` |
| **nginx / proxy inverso** | Servidor que recibe el tráfico público y lo reparte a los servicios internos | La recepción de un hotel | `infra/hardening/nginx-trackflow.conf` |
| **Puerto** | Número que identifica un servicio dentro de una máquina | El número de puerta de un piso | 3000, 8000/8001, 8010, 8020, 6379 |
| <a id="g-ttl"></a>**TTL** | Tiempo de vida de un dato antes de caducar | La fecha de caducidad de un yogur | Caché (45 s/20 s), memoria del agente (180 días) |
| **uv / venv / lockfile** | uv instala dependencias; un *venv* es un entorno aislado; el *lockfile* fija versiones exactas | Una despensa separada por cocina, con la lista de compra exacta | `.venv/`, `uv.lock`, `package-lock.json` |

### 17.9 Seguridad y normativa

| Término | Definición muy básica | Analogía | Dónde en TrackFlow |
| --- | --- | --- | --- |
| <a id="g-acl"></a>**Control de acceso (ACL)** | Reglas de quién puede ver o hacer qué | La lista de llaves de cada empleado | ACL de pedidos (`order_access.py`), roles admin/manager |
| <a id="g-ccpa"></a>**CCPA / CPRA** | Ley de privacidad de California (acceso, borrado, *opt-out*, aviso de brechas) | El RGPD californiano | Operación de Los Ángeles (paso 35) |
| **CVE / GHSA** | Identificador público de una vulnerabilidad conocida | El número de expediente de un fallo | `audit/security/before/*` |
| **detect-secrets / pip-audit / npm audit** | Escáneres de secretos en el código / de dependencias vulnerables | Detectores de metales | Pasos 34-35 |
| <a id="g-firewall"></a>**Firewall (ufw)** | Filtro que decide qué conexiones de red se permiten | El portero de una discoteca | `provision.sh` (22/80/443) |
| <a id="g-guardrail"></a>**Guardrail** | Control que impide a un agente hacer o decir lo que no debe | La barandilla de un puente | `guardrails.py` |
| **Harness** | Conjunto de controles y pruebas alrededor de un agente | El arnés de un escalador | Paso 28 |
| <a id="g-hardening"></a>**Hardening (endurecimiento)** | Reducir la superficie de ataque de un servidor | Poner rejas y cerraduras en casa | `infra/hardening/` (paso 34) |
| <a id="g-hash"></a>**Hash** | Huella irreversible de un dato (no se puede "deshacer") | Una huella dactilar: identifica, pero no reconstruye a la persona | Contraseñas |
| <a id="g-jailbreak"></a>**Jailbreak** | Intento de que un LLM ignore sus reglas | Convencer al guardia de que te deje pasar sin entrada | `check_instruction_override` |
| <a id="g-jwt"></a>**JWT** | Token firmado que demuestra quién eres | Una pulsera de festival con sello oficial | Login, `Authorization: Bearer` |
| <a id="g-nist"></a>**NIST CSF** | Marco de ciberseguridad con 6 funciones: Govern, Identify, Protect, Detect, Respond, Recover | Un plan de emergencias por fases | Informe del paso 35 |
| <a id="g-unicode"></a>**Normalización Unicode (NFKC)** | Convertir variantes de caracteres a una forma estándar | Pasar todas las letras "de adorno" a letra normal | `input_sanitization.py` (paso 35) |
| <a id="g-oauth"></a>**OAuth 2.1** | Estándar para dar acceso limitado con tokens, sin compartir contraseñas | Una llave de aparcacoches que solo arranca el coche | Servidor MCP (paso 26) |
| <a id="g-oidc"></a>**OIDC** | Capa de identidad sobre OAuth (quién es el usuario o servicio) | El DNI que acompaña a la llave | `MCPAUTH_ISSUER`, `dev_idp_server.py` |
| <a id="g-owasp"></a>**OWASP Top 10** | Lista de los 10 riesgos de seguridad web más comunes (A01 control de acceso, A02 criptografía, A03 inyección…) | La lista de los 10 robos más frecuentes | Auditoría del paso 34 |
| <a id="g-injection"></a>**Prompt injection (directa / indirecta)** | Meter instrucciones maliciosas al LLM, por el usuario (directa) o escondidas en documentos o tools (indirecta) | Una nota falsa del jefe colada entre los papeles | Pasos 28, 34, 35 |
| <a id="g-ratelimit"></a>**Rate limiting** | Límite de peticiones por usuario y tiempo | Un máximo de 2 cafés gratis por persona y hora | `rate_limit.py` (429) |
| <a id="g-rce"></a>**RCE** | Ejecución remota de código: un atacante ejecuta lo que quiere en tu servidor | Que un desconocido use tu ordenador a distancia | Vulnerabilidad de `next` 16.2.9 (paso 34) |
| <a id="g-rgpd"></a>**RGPD / AEPD** | Ley europea de protección de datos / autoridad española que la vigila (aviso de brecha en 72 h) | El reglamento de privacidad y su inspector | Paso 35 |
| <a id="g-scope"></a>**Scope** | Permiso concreto dentro de un token | Las zonas a las que te deja pasar una pulsera VIP | `incidents:read`, `inventory:read` |
| <a id="g-scrypt"></a>**scrypt** | Algoritmo de hash de contraseñas lento a propósito y con mucha memoria | Una caja fuerte que tarda en abrirse incluso con la combinación | `password_hashing.py` (paso 34) |
| <a id="g-secdesign"></a>**Seguridad por diseño** | Pensar la seguridad desde el principio, no añadirla al final | Diseñar el edificio con salidas de emergencia | Paso 35 |
| <a id="g-ssh"></a>**SSH** | Conexión remota cifrada a un servidor | Un túnel privado hasta la sala de máquinas | `sshd` endurecido (paso 34) |
| **sudo / root** | `root` es el superusuario; `sudo` permite ejecutar algo como él | La llave maestra / pedirla prestada para una tarea | `trackops` con sudo limitado |
| <a id="g-tls"></a>**TLS / HSTS** | Cifrado de las conexiones (el candado de HTTPS) / orden al navegador de usar siempre HTTPS | Un sobre cerrado / "solo acepto sobres cerrados" | Plantilla nginx (paso 34) |
| **XSS** | Inyectar JavaScript malicioso en una web | Una nota trampa pegada en el tablón | Riesgo para el JWT en `localStorage` |

### 17.10 Otros conceptos del proyecto

| Término | Definición muy básica | Dónde en TrackFlow |
| --- | --- | --- |
| <a id="g-evento"></a>**Evento (de telemetría)** | Registro de que algo pasó, con fecha y datos | `inbound_order_created`, `route_changed` |
| <a id="g-telemetria"></a>**Telemetría** | Medir automáticamente lo que ocurre en un sistema | `services/telemetry.ts`, `telemetry_events` |
| **Última milla** | Última etapa del envío: del almacén al cliente | El negocio de TrackFlow |
| **B2B / B2C** | Negocio con empresas (las marcas) / con consumidores finales (los destinatarios) | Clientes de TrackFlow |
| **Semana ISO** | Numeración estándar de semanas (`2026-W35`) | Pipeline de KPIs |

### 17.11 Archivos generados y del editor (se pueden ignorar)

| Carpeta / archivo | Qué es | ¿Hay que tocarlo? |
| --- | --- | --- |
| `__pycache__/` | Python guarda aquí versiones "precompiladas" de los `.py` para arrancar más rápido. Se regenera solo | No. Si da problemas, se puede borrar sin riesgo |
| `.pytest_cache/` | pytest guarda qué tests fallaron la última vez, para poder relanzar solo esos | No |
| `.vscode/` | Configuración del editor Visual Studio Code (extensiones recomendadas, ajustes) | No afecta a la aplicación |
| `.venv/` | Entorno virtual con las librerías instaladas de cada servicio | No; se recrea con `uv sync` |
| `node_modules/` | Librerías de JavaScript instaladas | No; se recrea con `npm install` |
| `.next/` | Compilación de Next.js | No; se recrea con `npm run build` |
| `*.egg-info/` | Metadatos de instalación de un paquete Python | No |
| `.env` | Tus secretos locales (**nunca** se suben a git) | Sí: lo creas tú a partir del `.env.example` |
