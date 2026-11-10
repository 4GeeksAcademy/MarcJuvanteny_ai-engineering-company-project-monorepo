# Chat en tiempo real con el First-line CX agent (WebSocket) — Hito 10 · Parte 2

Fecha: 2026-10-28

Implementación de `CONTEXT/CONTEXT10.md`, Parte 2 ("BRIEFING — TrackFlow:
Sistemas en Tiempo Real (Parte 2)"), pedida por **Valentina Cruz**
(Customer Experience). Antes, el cliente mandaba un mensaje y recibía la
respuesta completa de una sola vez. Si el agente estaba respondiendo al
intent equivocado (rastreo cuando querían una devolución), no se podía
redirigir hasta que terminara. Ahora:

- la respuesta llega **token a token** por un WebSocket;
- se puede **interrumpir a mitad de respuesta**: el stream se aborta de
  verdad, el parcial queda marcado como `interrupted` y la nueva entrada
  arranca un turno nuevo;
- al reconectar, la conversación se **rehidrata** (historial + hilo de
  LangGraph) antes de aceptar tokens nuevos.

El agente es el mismo de Hitos 7–8 (`services/knowledge-api/agent_graph.py`):
mismos nodos, mismas tools, mismos guardrails y memoria. Solo cambia el
canal (CONTEXT10.md §2).

## Dónde vive el código

```
services/knowledge-api/
  chat_sessions.py        # NUEVO -- ChatSession (campos del BRIEFING §3) + historial ChatMessage
  chat_pubsub.py           # NUEVO -- pub/sub en memoria, un canal por sesión: chat.<session_id>
  chat_runner.py            # NUEVO -- PRODUCTOR: ChatManager, turnos, abort, interrupción
  chat_auth.py               # NUEVO -- verifica el JWT del backoffice (mismo secreto que incidents-api)
  routers/chat.py             # NUEVO -- CONSUMIDORES: POST /chat/sessions, WS /chat/ws
  agent_graph.py              # EXTENDIDO -- generate en streaming OPCIONAL (stream_mode="custom") + on_token en run_agent
  main.py                      # EXTENDIDO -- app.include_router(chat_router)
  pyproject.toml / uv.lock      # EXTENDIDO -- PyJWT declarado (ya estaba en el venv, ahora explícito)
  .env.example                  # EXTENDIDO -- JWT_SECRET_KEY

data/pipelines/rag.py           # EXTENDIDO -- astream_answer(): mismo prompt/modelo que generate_answer, en streaming

uis/backoffice/src/
  lib/use-cx-chat.ts                  # NUEVO -- WebSocket, backoff, rehidratación, dedupe por sequence
  components/knowledge-query-panel.tsx # REESCRITO -- de petición/respuesta única a chat por WebSocket
  lib/knowledge.ts                     # queryKnowledgeBase() eliminado (sin usos); queda KNOWLEDGE_API_URL
  app/(protected)/knowledge/page.tsx   # subtítulo
  app/globals.css                      # .chat-* (burbujas, cursor de escritura, "Interrumpida")

tests/services/test_chat_websocket.py  # NUEVO -- 15 pruebas, grafo real del agente con fakes inyectados
```

## Contrato

**Entidad** (`chat_sessions.py`, nombres exactos de CONTEXT10.md §3):

```json
{"session_id": "chat_1a2b3c4d5e6f", "agent_id": "first_line_cx", "user_id": "42",
 "client_id": "cli_7f3a", "status": "active", "created_at": "2026-10-28T18:00:00Z"}
```

`status ∈ {active, interrupted, closed}`. El `session_id` **es** el
`thread_id` de LangGraph del agente. Un solo id para la misma sesión,
nunca uno paralelo.

**Crear sesión**: `POST /chat/sessions` con `Authorization: Bearer <JWT>` y
body `{"client_id": "..."}` opcional → `201` + la sesión. Sin JWT válido →
`401`. Cerrar: `POST /chat/sessions/{session_id}/close`.

**Conectar**: `WS /chat/ws?session_id=<id>&token=<JWT>`. El navegador no
puede mandar `Authorization` en el handshake de un WebSocket, así que el
token va en `?token=`. Se rechaza **antes de cualquier evento de chat**
(se acepta el handshake solo para que el código de cierre llegue legible al
navegador; un rechazo en el handshake le llega como un 1006 genérico):

| Código | Motivo | El cliente… |
| --- | --- | --- |
| 4401 | sin token, token inválido, expirado o con otro secreto | no reintenta (sesión del backoffice vencida) |
| 4400 | falta `session_id` | — |
| 4403 | la sesión es de otro usuario | crea una sesión nueva |
| 4404 | la sesión no existe | crea una sesión nueva y avisa |
| 4410 | la sesión está cerrada | crea una sesión nueva y avisa |

**Eventos** (`{"event": ..., "data": {...}}`, CONTEXT10.md §4):

| Dirección | Evento | `data` |
| --- | --- | --- |
| C → S | `user_message` | `session_id`, `text` |
| C → S | `interrupt_requested` | `session_id`, `new_input` (o `null` = solo detener) |
| S → C | `session_snapshot` | `session_id`, `status`, `messages[]` — **siempre lo primero** tras conectar |
| S → C | `user_message` | `session_id`, `message_id`, `text` (eco del turno, también a otras pestañas) |
| S → C | `token_chunk` | `session_id`, `message_id`, `token`, `sequence` |
| S → C | `generation_interrupted` | `session_id`, `message_id`, `status: "interrupted"` |
| S → C | `generation_completed` | `session_id`, `message_id` |
| S → C | `error` | `session_id`, `detail` (frame de otra sesión, evento desconocido) |

`messages[]` del snapshot: `{message_id, role, text, status
("complete"|"streaming"|"interrupted"), sequence, created_at}`.

Ningún payload de la Parte 1 (RFP/SSE) se mezcla en este contrato.

## Decisiones

**Streaming con el modo de LangGraph que corresponde: `custom`.**
`generate` llama al LLM con el cliente de OpenAI directamente, no con un
chat model de LangChain, así que `stream_mode="messages"` no vería sus
tokens. `build_graph()`/`run_agent()` aceptan un `astream_generate_fn`
**opcional**. Si se pasa, el nodo `generate` es async, itera
`rag.astream_answer()` (mismo prompt, mismo modelo, mismo
`AGENT_SYSTEM_PROMPT`, misma sanitización y auditoría) y emite cada token
con `get_stream_writer()`. `run_agent` corre con
`stream_mode=["updates", "custom"]` y entrega cada token a `on_token`. Sin
esos parámetros (`POST /agent/query`, los 74 tests existentes) el grafo es
idéntico al de antes.

**Abort real, no `interrupt()`.** Cada turno es una `asyncio.Task`.
`interrupt_requested`, o un `user_message` mientras el agente responde,
hace `task.cancel()`. La cancelación entra en el `astream()` de LangGraph
y en el `async for` del stream del LLM (que cierra la conexión HTTP del
modelo: no queda generando en segundo plano). Los `token_chunk` solo se
publican desde esa tarea, así que después del cancel no sale ninguno más.
No se usa `interrupt()` de LangGraph: eso es una pausa HITL del grafo, no un
abort de streaming.

**Después del abort** (`ChatManager._abort_running`): el mensaje del
asistente queda en el historial con `status = "interrupted"` y exactamente
los tokens ya emitidos; la sesión pasa a `interrupted`; se publica
`generation_interrupted`; y `new_input` arranca un turno **nuevo** (otro
`message_id`, la sesión vuelve a `active`). El mensaje interrumpido nunca
se borra ni se sobrescribe.

**Pub/sub productor/consumidor** (`chat_pubsub.py`, CONTEXT10.md §5). Un
canal por sesión, `chat.<session_id>`. El productor (`ChatManager`) no
conoce ningún WebSocket; cada conexión es un suscriptor con su propia
`asyncio.Queue`. Consecuencias:
- cerrar el socket **no** aborta la generación: el agente termina y el
  texto queda en el historial (solo una interrupción explícita aborta);
- varias pestañas de la misma sesión reciben los mismos eventos;
- en memoria, como permite el BRIEFING para un solo proceso. Con varios
  workers, la misma interfaz `publish/subscribe` se respalda con Redis
  pub/sub sin tocar productor ni consumidores.

**Rehidratación al reconectar, sin perder el hilo.**
1. El cliente reenvía el mismo `session_id` (guardado en `localStorage`,
   así que sobrevive también a recargar la página).
2. El servidor se suscribe al canal **antes** de armar el snapshot (ningún
   token cae en el hueco) y manda `session_snapshot` primero: historial
   completo, incluido el mensaje que sigue en `streaming` con su texto y su
   `sequence`.
3. Los tokens ya incluidos en el snapshot se filtran por `sequence` en el
   servidor, y el cliente vuelve a filtrar por si acaso. El cliente además
   ignora todo `token_chunk` hasta haber aplicado el snapshot: **primero
   contexto, después tokens nuevos**.
4. Contexto del agente: como `session_id` = `thread_id`, el checkpointer de
   LangGraph (`_DEFAULT_CHECKPOINTER`) sigue el mismo hilo; por ejemplo, una
   `pending_memory_proposal` de Hito 8 sobrevive a la reconexión.

**Guardrail de salida.** `output_guard`/`propose_memory` corren después de
`generate`. Si añaden un sufijo (redirección, propuesta de memoria), se
emite como más `token_chunk`. Si **reemplazan** la respuesta (fuga de datos
sensibles), el historial guarda la versión segura y se publica un
`session_snapshot` para que todos los clientes reemplacen lo que
mostraron. Las rutas sin LLM (`no_context`, `guardrail_blocked`,
`tool_failed`) se emiten por palabra, así que la UI siempre ve streaming.
Límite conocido: durante el reemplazo, el cliente llegó a ver los tokens
originales unos instantes. Bufferizar toda la respuesta para validarla
antes anularía el streaming; la validación por fragmentos queda como
mejora futura.

**JWT.** `chat_auth.py` verifica firma + expiración con el mismo
`JWT_SECRET_KEY` y HS256 con que `services/incidents-api` emite el token,
y usa `sub` como `user_id`. Este servicio nunca emite tokens. Se valida al
conectar; un token que vence con el socket abierto se vuelve a validar en
la siguiente reconexión (→ 4401). `?token=` puede aparecer en logs de
acceso de un proxy: en producción conviene un token de corta vida
específico para el socket.

**`client_id`** llega opcional en `POST /chat/sessions`: el JWT del
backoffice no lo trae (`sub` + `role`). Es un id opaco, nunca el nombre de
la marca (techContext).

**Persistencia.** Sesiones e historial viven en memoria, igual que el
`MemorySaver` del agente: sobreviven a reconexiones del WebSocket, no a un
reinicio del servicio. Tras un reinicio, el `session_id` guardado da 4404 y
la UI abre una sesión nueva y avisa. Persistirlo en Postgres (y pasar el
agente a `PostgresSaver`, como ya hace el flujo de RFPs) es el siguiente
paso si se necesita.

**UI** (`/knowledge`, el panel de chat que ya existía, ahora contra el
First-line CX agent):
- burbujas de usuario/agente, con el texto creciendo en vivo y un cursor
  de escritura;
- mientras responde, aparece "Detener" (`interrupt_requested` sin
  `new_input`), y escribir + Enter **interrumpe y redirige**
  (`interrupt_requested` con `new_input`);
- el parcial queda visible con borde discontinuo y la etiqueta
  "Interrumpida"; la respuesta redirigida aparece como un mensaje nuevo;
- indicador de conexión: "Conectado" / "Reconectando en Ns (intento n)" /
  "Sin sesión";
- reconexión con backoff 1 s → 30 s, jitter ±20 %, reiniciado al recibir el
  snapshot.

## Cómo correrlo

```bash
# services/knowledge-api/.env: JWT_SECRET_KEY = el MISMO valor que en services/incidents-api/.env
cd services/knowledge-api && uvicorn main:app --reload --port 8020
cd services/incidents-api && uvicorn main:app --reload --port 8001   # emite el JWT (login)
cd uis/backoffice && npm run dev                                       # http://localhost:3000/knowledge
```

```bash
# Tests (cada archivo de tests/services corre con el venv de su servicio y salta el otro)
cd services/knowledge-api && .venv/bin/python -m pytest ../../tests/services -q
```

## Checklist de la entrega

Backend (`services/`)
- [x] Endpoint WebSocket con una conexión persistente por sesión de chat — `WS /chat/ws`.
- [x] Mismo JWT que el backoffice, por `?token=`; sin token o con token inválido se cierra con 4401 antes de cualquier evento.
- [x] `session_id` obligatorio en la URL, ligado a una sesión existente del mismo usuario; es también el `thread_id` de LangGraph.
- [x] Respuesta token a token con `stream_mode="custom"` de LangGraph.
- [x] Abort real del stream en curso (`task.cancel()` → `astream` → stream del LLM); sin `interrupt()` HITL.
- [x] Parcial marcado `interrupted` y conservado; la nueva entrada arranca un turno nuevo.
- [x] Productor desacoplado de las conexiones por pub/sub (`chat.<session_id>`).

Frontend (`uis/`)
- [x] El chat existente usa WebSocket en lugar de petición/respuesta única.
- [x] Escritura en vivo token a token.
- [x] Control de interrupción ("Detener" + enviar mientras responde); parcial visible como "Interrumpida"; respuesta redirigida como mensaje nuevo.
- [x] Reconexión con backoff progresivo, mismo `session_id`, rehidratación por `session_snapshot` antes de aceptar tokens nuevos.

## Cómo se verificó

```
$ cd services/knowledge-api && .venv/bin/python -m pytest ../../tests/services -q
15 passed, 1 skipped          (2 corridas; el skip es el test SSE de la Parte 1, otro venv)

$ .venv/bin/python -m pytest ../../tests/pipelines/test_agent_graph.py \
    ../../tests/pipelines/test_agent_memory.py ../../tests/pipelines/test_agent_guardrails.py -q
74 passed                     (sin cambios: el grafo por defecto es idéntico)

$ cd services/incidents-api && uv run --group dev pytest ../../tests/services -q
10 passed, 1 skipped          (Parte 1 intacta)

$ cd uis/backoffice && npx tsc --noEmit -p . && npx eslint <archivos tocados>   # OK
```

`tests/services/test_chat_websocket.py` corre el **grafo real** del agente
(`run_agent`) con las dependencias externas sustituidas: chunk RAG fijo, un
"LLM" que es un generador async con pausa entre tokens, y un `MemorySaver`
fresco. Así el streaming pasa de verdad por `stream_mode="custom"` y el
abort, por la cancelación de `astream()`. Cubre:

- campos de `ChatSession` exactamente los del BRIEFING; `POST /chat/sessions` sin JWT → 401;
- WebSocket sin token, con basura, expirado o con otro secreto → **4401
  como primer y único frame** (nunca un `session_snapshot`);
- sin `session_id` → 4400, sesión inexistente → 4404, sesión de otro usuario → 4403;
- `session_snapshot` primero; eco `user_message`; un `token_chunk` por
  token, en orden, `sequence` 0..n; `generation_completed`;
- **interrupción**: `generation_interrupted` con el `message_id` correcto,
  **ningún** `token_chunk` de esa generación después, el "LLM" recibió la
  cancelación, el turno nuevo tiene otro `message_id` y llega completo, y el
  historial es `user/complete, assistant/interrupted, user/complete,
  assistant/complete`, con el parcial igual a lo que el cliente vio;
- un `user_message` durante la generación también interrumpe;
- **reconexión a mitad de respuesta**: el productor sigue con el socket
  cerrado; al volver llega el snapshot con el mensaje en `streaming`, y
  después solo tokens con `sequence` posterior; snapshot + resto = la
  respuesta completa, sin duplicados ni huecos;
- reconexión tras terminar: el snapshot restaura el hilo entero;
- `session_id` = `thread_id`: el checkpoint de LangGraph del hilo tiene la pregunta y la respuesta;
- pub/sub: dos suscriptores reciben eventos idénticos; sin suscriptores el turno se completa igual;
- un reemplazo por `output_guard` llega como `session_snapshot` con el texto seguro;
- un frame con el `session_id` de otra sesión → `error`.

Notas:
- La UI no se probó en un navegador en esta sesión (no hay Qdrant/LLM
  levantados para el agente real). El protocolo que implementa
  `use-cx-chat.ts` (snapshot primero, filtro por `sequence`, códigos de
  cierre) es el que cubren los tests de arriba.
- Al correr los tests existentes del agente se generan
  `data/eval/agent-traces/*.json` y `data/eval/agent-guardrail-log.jsonl`
  (comportamiento previo de esos tests). Los nuevos tests de chat
  desactivan `_save_trace`.
