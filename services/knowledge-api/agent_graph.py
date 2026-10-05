"""Grafo del agente RAG de TrackFlow (`CONTEXT/CONTEXT7.md`, secciones
"Grafo del agente" + "Tool obligatoria" + "Enrutamiento del agente" — el
"proyecto posterior" que `data/pipelines/rag.py` dejó preparado desde la
Fase 2: `retrieve()` y `generate_answer()` separados de `query()`
precisamente para que un grafo como este pudiera reutilizarlos como pasos
independientes, sin ejecutar la recuperación dos veces).

## Migración a MCP (checklist "Migración del agente")

Los nodos `incidents_tool`/`inventory_tool` ya NO llaman directamente a
`services/incidents-api` por HTTP -- pasan por `mcps/trackflow-mcp` (el MCP
Server) vía `langchain-mcp-adapters` (`mcp_client.py::call_mcp_tool`). La
implementación HTTP directa anterior (`tools/incidents_tool.py`,
`tools/inventory_tool.py`) se **eliminó** (no se dejó deprecada-pero-viva):
el agente tiene un único camino posible hacia el Incidents Manager, nunca
dos. El contrato de estos dos nodos no cambió (siguen devolviendo
`{"ok": ..., "incidents"|"products": [...], "error": ...}` en
`tool_result`), así que el resto del grafo (enrutamiento, `tool_failed`,
`_tool_result_to_context_chunks`) no se tocó.

Como las llamadas MCP son async (`langchain_mcp_adapters`), `incidents_tool`
e `inventory_tool` ahora son nodos `async def` -- LangGraph soporta nodos
sync y async mezclados en el mismo grafo bajo `.astream()`/`.ainvoke()`
(verificado con un grafo mínimo de prueba antes de migrar, no asumido).
`run_agent()` pasó de `compiled_graph.stream(...)` a
`await compiled_graph.astream(...)`, y `routers/agent.py::query_agent` pasó
a `async def` -- FastAPI soporta handlers async nativamente, cambio
mínimo.

## Memoria y auto-mejora (checklist "Memoria y Auto-mejora de Agentes",
## `CONTEXT/CONTEXT8.md`)

Dos nodos nuevos, nunca una segunda llamada al modelo ni un agente aparte:

- `retrieve_memory`: corre siempre después de `classify_intent`, antes de
  cualquier ruta (RAG/tool/ambos). Si la pregunta menciona un carrier
  conocido, busca en `memory_store` (Redis, namespace `agent_memory:*` --
  NUNCA las colecciones RAG de Qdrant) una entrada ya aprobada para
  `carrier:país` y la agrega como contexto extra para `generate`. Lado de
  LECTURA de la interfaz explícita que pide el checklist.
- `propose_memory`: corre después de `generate`/`no_context` (no después de
  `tool_failed` -- un fallo de red no enseña nada nuevo que recordar).
  Evalúa la interacción (`memory_proposal.py::evaluate_for_memory_proposal`,
  heurística determinista, mismo stand-in documentado que `classify_intent`)
  y, si hay algo memorable, lo agrega como pregunta al final de la MISMA
  respuesta (`state["answer"]`) y guarda la propuesta en
  `state["pending_memory_proposal"]` -- nunca escribe a memoria en este
  paso.
- `resolve_pending_memory_proposal`: corre al principio del turno
  SIGUIENTE, solo si `receive_question` detecta un
  `pending_memory_proposal` que sobrevivió del turno anterior (vía el
  checkpointer compartido -- ver `_DEFAULT_CHECKPOINTER` más abajo).
  Clasifica la respuesta del usuario
  (`memory_decision.py::classify_memory_decision` -- aprobado/rechazado/
  editado, nunca un `"sí" in mensaje`), escribe a `memory_store` SOLO si
  fue aprobada o editada, y registra la decisión en
  `memory_audit.py` sin importar el resultado. Siempre continúa hacia
  `classify_intent` después -- el mismo mensaje puede resolver la
  propuesta Y traer una pregunta nueva.

"Una sola propuesta pendiente a la vez" queda garantizado por construcción:
`propose_memory` solo se alcanza después de que `resolve_pending_memory_proposal`
(si corrió este turno) ya limpió `pending_memory_proposal` -- nunca hay un
momento del grafo en el que se pueda crear una propuesta nueva mientras
otra sigue sin resolver.

## Harness y guardrails (`CONTEXT/CONTEXT8.2.md`, Hito 8 Parte 2)

Asegura este MISMO agente -- no hay un agente paralelo para este sprint
(`CONTEXT8.2.md`, Sección 1: "mantén esa identidad"). Dos nodos nuevos, más
una sanitización dentro de `generate`, implementados en `guardrails.py`:

- `input_guard`: corre primero de todos, antes incluso de
  `resolve_pending_memory_proposal` -- la seguridad tiene prioridad sobre
  la memoria. Revisa (en orden) intento de cambio de instrucciones, uso
  personal no relacionado, mezcla de políticas entre países, y
  autorización de sesión sobre el número de pedido mencionado. El primero
  que dispara **bloquea** (`guardrail_blocked=True`, `answer` pasa a ser
  el mensaje del guardrail, el grafo corta a `END` sin llegar a
  `retrieve`/tools/`generate`). Si ninguno bloquea pero la pregunta es
  casual/general, guarda un sufijo de redirección
  (`guardrail_redirect_suffix`) para anexar a la respuesta real más
  adelante -- una pregunta casual SIGUE respondida, nunca bloqueada.
- `generate` (extendido): sanitiza con `sanitize_external_content()` los
  chunks de tool/RAG/memoria ANTES de pasarlos a `generate_fn` -- ningún
  texto externo puede tratarse como instrucción, ni siquiera si contiene
  frases con forma de instrucción (defensa en profundidad, además del
  aislamiento estructural ya dado por `_build_prompt()`, que pone ese
  contenido en el mensaje de rol `user`, nunca en el `system`).
- `output_guard`: corre después de `generate`/`no_context`. Valida la
  salida (`validate_output()` -- formato, fuga del system prompt, datos
  sensibles del CONTEXT) y, si hace falta, reemplaza la respuesta por un
  mensaje seguro. También anexa `guardrail_redirect_suffix` si
  `input_guard` lo dejó pendiente.

El `AGENT_SYSTEM_PROMPT` real (separación explícita instrucciones/input,
dominio declarado, qué nunca revelar) vive en `guardrails.py` -- inyectado
en `generate_answer()` de `data/pipelines/rag.py` vía su nuevo parámetro
`system_prompt`, sin duplicar esa función.

## Estado del grafo

`AgentState` trae lo mínimo que un nodo necesita para decidir el siguiente
paso: la pregunta, la ruta elegida (`route`), el contexto RAG ya recuperado,
el resultado crudo de una tool (o `None`), la respuesta final, y un mensaje
de error para la ruta de pregunta vacía. **Deliberadamente no incluye
historial de conversación**: cada corrida resuelve una sola pregunta
independiente — no hay un caso de uso todavía que justifique cargar turnos
anteriores en el estado.

## Nodos y su contrato

- `receive_question`: recibe la pregunta, la normaliza (`strip()`).
- `classify_intent`: decide `route` (`"rag"` | `"incidents_tool"` |
  `"inventory_tool"` | `"both"`) a partir de la pregunta — ver
  `classify_intent()` más abajo.
- `retrieve`: llama a `retrieve()` de `data/pipelines/rag.py` **sin
  duplicarlo**.
- `incidents_tool` / `inventory_tool`: cada una llama a **una sola** tool
  del MCP Server (ver "Migración a MCP" más abajo) — nunca una tool que
  "busca tickets o inventario según el caso". Ambas son de solo lectura,
  con timeout explícito (`mcp_client.py::MCP_TIMEOUT_SECONDS`) y devuelven
  un resultado tipado con `ok: bool` — nunca lanzan la excepción cruda
  hacia el grafo.
- `tool_failed`: la tool agotó el timeout, falló, o el ticket/SKU no existe
  — responde con honestidad ("no pude confirmar...") **sin** llamar al
  modelo de generación, para que un fallo de red nunca se disfrace de un
  estado inventado. **Nunca** pasa por `propose_memory` después: un fallo
  no enseña nada nuevo que recordar.
- `retrieve_memory`: lado de LECTURA de la memoria (ver "Memoria y
  auto-mejora" más abajo) — corre siempre, para toda ruta.
- `generate`: llama a `generate_answer(question, context)` — **no** a
  `query()` — con el contexto RAG **y/o** el resultado de una tool exitosa
  (convertido a chunks de contexto por `_tool_result_to_context_chunks()`)
  **y/o** memoria aprobada relevante (`memory_context`), mismo formato que
  un chunk de Qdrant en los tres casos, para no tener que cambiar la firma
  de `generate_answer()`. Meter `query()` en este nodo volvería a ejecutar
  la recuperación y colapsaría el grafo a la secuencia monolítica que la
  guía pide evitar.
- `no_context`: responde con honestidad, sin llamar al LLM, cuando ni el RAG
  ni una tool trajeron nada.
- `empty_question`: la pregunta llegó vacía — nunca se llama a `retrieve()`
  ni a una tool con una query vacía.
- `propose_memory` / `resolve_pending_memory_proposal`: ver "Memoria y
  auto-mejora" más abajo.

## Enrutamiento (`classify_intent`)

Heurística determinista por palabras clave — un stand-in documentado de lo
que idealmente sería una clasificación por LLM (`GENERATION_MODEL`): sin
credenciales reales de 4Geeks en este repo no se puede probar esa versión de
forma confiable y offline, así que se implementa con un método 100%
verificable en tests. El punto de inyección (`classify_fn` en
`build_graph()`) ya deja lista la sustitución por un router basado en LLM el
día que haya credenciales.

## Aristas condicionales (no una secuencia fija)

```
START -> receive_question -> input_guard

input_guard -> [vacía]                        -> empty_question -> END
            -> [bloqueada por un guardrail]   -> guardrail_blocked -> END
            -> [hay pending_memory_proposal]  -> resolve_pending_memory_proposal -> classify_intent
            -> [con contenido, sin pendiente] -> classify_intent

classify_intent -> retrieve_memory

retrieve_memory -> [route="rag"]             -> retrieve
                 -> [route="incidents_tool"] -> incidents_tool
                 -> [route="inventory_tool"] -> inventory_tool
                 -> [route="both"]           -> incidents_tool (y luego retrieve)

incidents_tool -> [route="both"]          -> retrieve
               -> [tool ok]               -> generate
               -> [tool falló]            -> tool_failed -> END

inventory_tool -> [tool ok] -> generate
               -> [tool falló] -> tool_failed -> END

retrieve -> [sin contexto RAG Y sin tool ok] -> no_context -> output_guard
         -> [hay contexto RAG o tool ok]     -> generate -> output_guard

output_guard -> propose_memory -> END
```

## Checkpointing

`build_graph()` compila con un `checkpointer` (por defecto
`_DEFAULT_CHECKPOINTER`, un único `MemorySaver` a nivel de módulo
compartido entre corridas -- ver el comentario junto a su definición más
abajo sobre el bug real que esto corrigió: antes, cada `run_agent()` sin
`checkpointer` explícito creaba un `MemorySaver` nuevo, y nada sobrevivía
entre dos requests HTTP separados con el mismo `thread_id`. Sigue sin
persistir entre reinicios del proceso -- para eso hace falta
`SqliteSaver`/`PostgresSaver` de `langgraph-checkpoint-*`, no incluido en
esta entrega, ver `Pasos/`). Cada nodo ejecutado queda como un checkpoint
bajo el mismo `thread_id` — `compiled_graph.get_state_history(config)`
permite inspeccionar o retomar una corrida existente, y es el mecanismo que
hace posible que `pending_memory_proposal` sobreviva al turno siguiente.

## Trace

`run_agent()` corre el grafo con `stream_mode="updates"` (LangGraph emite
`{nodo: cambio_de_estado}` en el orden real de ejecución) y guarda esa
secuencia en `data/eval/agent-traces/<thread_id>.json` — consultable después
de la corrida (`get_trace(thread_id)`). El orden de nodos en el trace
muestra con claridad si se usó el RAG (`retrieve`), una tool
(`incidents_tool`/`inventory_tool`), o ambos, y en qué orden.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

import pipeline_path  # noqa: F401  (efecto secundario: agrega data/pipelines/ a sys.path)
from rag import generate_answer, retrieve
from intent_extraction import extract_incident_query, extract_inventory_query
from mcp_client import call_mcp_tool
from memory_decision import MemoryDecision, classify_memory_decision
from memory_proposal import MemoryProposal, evaluate_for_memory_proposal, extract_carrier, extract_country
from guardrail_audit import record_guardrail_event
from guardrails import (
    AGENT_SYSTEM_PROMPT,
    GuardrailResult,
    check_casual_question,
    check_country_policy_mixing,
    check_instruction_override,
    check_personal_use_request,
    check_unauthorized_tracking_request,
    sanitize_external_content,
    validate_output,
)

SERVICE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SERVICE_DIR.parent.parent
TRACE_DIR = ROOT_DIR / "data" / "eval" / "agent-traces"

# Checkpointer compartido a nivel de módulo -- ver "Bug real encontrado"
# en Pasos/agent-memory.md: antes de esto, cada llamada a `run_agent()` sin
# un `checkpointer` explícito pasaba `None` a `build_graph()`, que creaba
# un `MemorySaver()` NUEVO en cada corrida (`checkpointer or MemorySaver()`)
# -- nada sobrevivía entre dos requests HTTP separados a `POST /agent/query`
# con el mismo `thread_id`, aunque el docstring de Hito 7 ya afirmaba
# soporte de checkpointing "para que una corrida pueda... retomarse". Con
# memoria (Hito 8: una propuesta pendiente debe sobrevivir al turno
# siguiente, que en producción es OTRA request HTTP) esto se vuelve
# load-bearing, no cosmético. Los tests que necesitan estado aislado siguen
# pudiendo pasar su propio `MemorySaver()` fresco explícito.
_DEFAULT_CHECKPOINTER = MemorySaver()

NO_CONTEXT_ANSWER = "No tengo información sobre eso en la base de conocimiento de TrackFlow."
EMPTY_QUESTION_ERROR = "La pregunta no puede estar vacía."

_INCIDENT_KEYWORDS = ("ticket", "tickets", "incidencia", "incidencias", "incident")
_INVENTORY_KEYWORDS = ("stock", "inventario", "unidades disponibles", "existencias")
_POLICY_KEYWORDS = ("política", "politica", "sla", "devolución", "devolucion", "cobertura", "tarifa", "descuento")


class AgentState(TypedDict, total=False):
    question: str
    thread_id: str
    route: str | None
    context: list[dict[str, Any]] | None
    memory_context: list[dict[str, Any]] | None
    tool_result: dict[str, Any] | None
    answer: str | None
    error: str | None
    pending_memory_proposal: dict[str, Any] | None
    memory_decision_record: dict[str, Any] | None
    # Hito 8 Parte 2 (CONTEXT8.2.md, harness y guardrails):
    authorized_order_ids: list[str] | None  # pedidos que la sesion actual puede consultar (ver guardrails.py)
    guardrail_blocked: bool | None
    guardrail_redirect_suffix: str | None


def classify_intent(question: str) -> str:
    """`"rag"` | `"incidents_tool"` | `"inventory_tool"` | `"both"` — ver
    "Enrutamiento" en el docstring del módulo."""
    lowered = question.lower()
    wants_incidents = any(keyword in lowered for keyword in _INCIDENT_KEYWORDS)
    wants_inventory = any(keyword in lowered for keyword in _INVENTORY_KEYWORDS)

    if wants_incidents:
        if any(keyword in lowered for keyword in _POLICY_KEYWORDS):
            return "both"
        return "incidents_tool"
    if wants_inventory:
        return "inventory_tool"
    return "rag"


def _receive_question_node(state: AgentState) -> dict[str, Any]:
    return {"question": (state.get("question") or "").strip()}


def _record_guardrail(result: GuardrailResult, state: AgentState, audit_fn: Callable[..., None]) -> None:
    audit_fn(
        guardrail_name=result.guardrail_name,
        category=result.category,
        action=result.action,
        question=state["question"],
        thread_id=state.get("thread_id", ""),
    )


def _make_input_guard_node(
    audit_fn: Callable[..., None] = record_guardrail_event,
) -> Callable[[AgentState], dict[str, Any]]:
    """`CONTEXT8.2.md`: corre primero de todos (incluso antes de
    `resolve_pending_memory_proposal` -- la seguridad tiene prioridad
    sobre la memoria). Ver "Harness y guardrails" en el docstring del
    módulo para el orden de chequeos y por qué una pregunta casual se
    redirige en vez de bloquearse."""

    def input_guard_node(state: AgentState) -> dict[str, Any]:
        question = state["question"]
        if not question:
            return {}

        for check_fn in (check_instruction_override, check_personal_use_request, check_country_policy_mixing):
            result = check_fn(question)
            if result is not None:
                _record_guardrail(result, state, audit_fn)
                return {"guardrail_blocked": True, "answer": result.message}

        auth_result = check_unauthorized_tracking_request(question, state.get("authorized_order_ids"))
        if auth_result is not None:
            _record_guardrail(auth_result, state, audit_fn)
            return {"guardrail_blocked": True, "answer": auth_result.message}

        casual_result = check_casual_question(question)
        if casual_result is not None:
            _record_guardrail(casual_result, state, audit_fn)
            return {"guardrail_redirect_suffix": casual_result.message}

        return {}

    return input_guard_node


def _guardrail_blocked_node(state: AgentState) -> dict[str, Any]:
    """Nodo terminal sin lógica propia -- `input_guard` ya dejó `answer`
    listo. Existe como paso separado solo para que el trace muestre con
    claridad que la corrida terminó acá por un guardrail, no por una
    respuesta generada."""

    return {}


def _default_write_memory(key: str, category: str, fact: str, source_thread_id: str) -> None:
    from memory_store import make_entry, write_memory

    write_memory(make_entry(key, category, fact, source_thread_id=source_thread_id))


def _default_read_memory(key: str):
    from memory_store import read_memory

    return read_memory(key)


def _default_record_memory_decision(**kwargs: Any) -> None:
    from memory_audit import record_memory_decision

    record_memory_decision(**kwargs)


def _make_resolve_pending_memory_proposal_node(
    decide_fn: Callable[[str], MemoryDecision] = classify_memory_decision,
    write_fn: Callable[[str, str, str, str], None] = _default_write_memory,
    audit_fn: Callable[..., None] = _default_record_memory_decision,
) -> Callable[[AgentState], dict[str, Any]]:
    """`CONTEXT8.md`, "Confirmación del Usuario y Registro Auditable" --
    corre solo cuando `pending_memory_proposal` sobrevivió del turno
    anterior (ver `_route_after_input_guard`). Escribe a memoria SOLO
    si la decisión es `"approved"`/`"edited"`; registra la decisión en
    auditoría SIEMPRE, sin importar el resultado."""

    def resolve_node(state: AgentState) -> dict[str, Any]:
        proposal = state.get("pending_memory_proposal") or {}
        message = state["question"]
        decision = decide_fn(message)
        audit_outcome = decision.outcome

        if decision.outcome in ("approved", "edited"):
            fact = decision.edited_fact if decision.outcome == "edited" else proposal.get("fact", "")
            try:
                write_fn(proposal.get("key", ""), proposal.get("category", ""), fact, state.get("thread_id", ""))
            except Exception as exc:
                # Nunca reportar "approved" en la auditoria si el write de
                # verdad fallo (Redis caido) -- el registro debe ser honesto.
                audit_outcome = f"{decision.outcome}_write_failed:{exc}"

        audit_fn(
            thread_id=state.get("thread_id", ""),
            proposal=proposal,
            outcome=audit_outcome,
            triggering_message=message,
            edited_fact=decision.edited_fact,
        )

        return {
            "pending_memory_proposal": None,
            "memory_decision_record": {"outcome": audit_outcome, "proposal": proposal},
        }

    return resolve_node


def _make_classify_node(classify_fn: Callable[[str], str]) -> Callable[[AgentState], dict[str, Any]]:
    def classify_node(state: AgentState) -> dict[str, Any]:
        return {"route": classify_fn(state["question"])}

    return classify_node


def _memory_chunk(fact: str, key: str) -> dict[str, Any]:
    return {"source_document": "agent-memory", "section": key, "text": fact}


def _make_retrieve_memory_node(
    read_fn: Callable[[str], Any] = _default_read_memory,
) -> Callable[[AgentState], dict[str, Any]]:
    """Lado de LECTURA de la interfaz explícita de memoria (`CONTEXT8.md`).
    Corre siempre, para toda ruta -- si la pregunta menciona un carrier
    conocido y hay una entrada aprobada para `carrier:país`, se agrega como
    contexto extra para `generate` (nunca se inyecta memoria directo al
    system prompt sin pasar por esta interfaz).

    Igual que las tools del MCP Server: un fallo leyendo memoria (Redis
    caído, timeout) nunca debe tumbar el turno completo -- se degrada a
    "sin memoria para esta pregunta" en vez de propagar la excepción cruda
    (que haría fallar hasta una pregunta de RAG que de pura casualidad
    menciona el nombre de un carrier)."""

    def retrieve_memory_node(state: AgentState) -> dict[str, Any]:
        question = state["question"]
        carrier = extract_carrier(question)
        if carrier is None:
            return {"memory_context": []}

        country = extract_country(question, carrier=carrier)
        try:
            entry = read_fn(f"{carrier}:{country}")
        except Exception:
            return {"memory_context": []}

        if entry is None:
            return {"memory_context": []}

        fact = entry.fact if hasattr(entry, "fact") else entry["fact"]
        key = entry.key if hasattr(entry, "key") else entry["key"]
        return {"memory_context": [_memory_chunk(fact, key)]}

    return retrieve_memory_node


def _make_retrieve_node(retrieve_fn: Callable[[str], list[dict[str, Any]]]) -> Callable[[AgentState], dict[str, Any]]:
    def retrieve_node(state: AgentState) -> dict[str, Any]:
        return {"context": retrieve_fn(state["question"])}

    return retrieve_node


async def _default_incidents_tool_call(args: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("query_incident_tool", args)


async def _default_inventory_tool_call(args: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("query_inventory_tool", args)


def _make_incidents_tool_node(
    incidents_tool_fn: Callable[[dict[str, Any]], Any],
) -> Callable[[AgentState], Any]:
    async def incidents_tool_node(state: AgentState) -> dict[str, Any]:
        query = extract_incident_query(state["question"])
        result = await incidents_tool_fn({"query": query})
        return {"tool_result": result}

    return incidents_tool_node


def _make_inventory_tool_node(
    inventory_tool_fn: Callable[[dict[str, Any]], Any],
) -> Callable[[AgentState], Any]:
    async def inventory_tool_node(state: AgentState) -> dict[str, Any]:
        query = extract_inventory_query(state["question"])
        result = await inventory_tool_fn({"query": query})
        return {"tool_result": result}

    return inventory_tool_node


def _tool_failed_node(state: AgentState) -> dict[str, Any]:
    tool_result = state.get("tool_result") or {}
    error = tool_result.get("error", "error desconocido")
    return {"answer": f"No pude confirmar esa información en este momento ({error}). Probá de nuevo en unos minutos."}


def _tool_result_to_context_chunks(tool_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Reformatea la salida de una tool como chunks (mismo shape que un
    resultado de `retrieve()`), para que `generate_answer(question, context)`
    no necesite una firma distinta según la fuente de datos."""
    if not tool_result:
        return []

    if not tool_result.get("ok"):
        error = tool_result.get("error", "error desconocido")
        return [
            {
                "source_document": "incidents-api",
                "section": "Estado de ticket",
                "text": f"No se pudo confirmar el estado del ticket solicitado ahora mismo ({error}).",
            }
        ]

    chunks: list[dict[str, Any]] = []
    for incident in tool_result.get("incidents", []):
        text = (
            f"Ticket #{incident['id']} — {incident['title']}\n"
            f"Estado: {incident['status']}. Categoría: {incident['category']}. "
            f"Origen: {incident['origin']}. Sede: {incident['branch']}.\n"
            f"Creado: {incident['created_at']}. Actualizado: {incident['updated_at']}."
        )
        chunks.append({"source_document": "incidents-api", "section": f"Ticket {incident['id']}", "text": text})

    for product in tool_result.get("products", []):
        text = (
            f"SKU {product['sku']} — {product['name']} ({product['client_name']}).\n"
            f"Categoría: {product['category']}. Almacén: {product['warehouse']}. "
            f"Stock actual: {product['current_stock']} unidades."
        )
        chunks.append({"source_document": "incidents-api", "section": f"Inventario {product['sku']}", "text": text})

    return chunks


def _make_generate_node(
    generate_fn: Callable[[str, list[dict[str, Any]]], str],
    sanitize_fn: Callable[[list[dict[str, Any]]], tuple[list[dict[str, Any]], bool]] = sanitize_external_content,
    audit_fn: Callable[..., None] = record_guardrail_event,
) -> Callable[[AgentState], dict[str, Any]]:
    def generate_node(state: AgentState) -> dict[str, Any]:
        context = list(state.get("context") or [])
        memory_context = list(state.get("memory_context") or [])
        tool_chunks = _tool_result_to_context_chunks(state.get("tool_result"))

        all_chunks = tool_chunks + memory_context + context
        sanitized_chunks, flagged = sanitize_fn(all_chunks)
        if flagged:
            audit_fn(
                guardrail_name="external_content_sanitized",
                category="security",
                action="redirect",
                question=state["question"],
                thread_id=state.get("thread_id", ""),
            )

        return {"answer": generate_fn(state["question"], sanitized_chunks)}

    return generate_node


def _make_output_guard_node(
    validate_fn: Callable[[str], GuardrailResult | None] = validate_output,
    audit_fn: Callable[..., None] = record_guardrail_event,
) -> Callable[[AgentState], dict[str, Any]]:
    """Corre después de `generate`/`no_context` -- valida la respuesta
    (formato, fuga del system prompt, datos sensibles) y anexa el sufijo
    de redirección que `input_guard` haya dejado pendiente (pregunta
    casual/general, `CONTEXT8.2.md` Sección 2)."""

    def output_guard_node(state: AgentState) -> dict[str, Any]:
        answer = state.get("answer") or ""
        result = validate_fn(answer)
        if result is not None:
            _record_guardrail(result, state, audit_fn)
            return {"answer": result.message}

        suffix = state.get("guardrail_redirect_suffix")
        if suffix:
            return {"answer": answer + suffix}

        return {}

    return output_guard_node


def _no_context_node(state: AgentState) -> dict[str, Any]:
    return {"answer": NO_CONTEXT_ANSWER}


def _empty_question_node(state: AgentState) -> dict[str, Any]:
    return {"error": EMPTY_QUESTION_ERROR}


def _make_propose_memory_node(
    evaluate_fn: Callable[[str, str], MemoryProposal | None] = evaluate_for_memory_proposal,
) -> Callable[[AgentState], dict[str, Any]]:
    """`CONTEXT8.md`, "Auto-evaluación y Propuesta de Memoria" -- corre
    después de `generate`/`no_context` (nunca después de `tool_failed`: un
    fallo de red no enseña nada nuevo). Nunca escribe a memoria acá --
    guarda la propuesta en `pending_memory_proposal` (el checkpointer la
    hace sobrevivir al turno siguiente) y se la propone al usuario dentro
    de la misma respuesta."""

    def propose_memory_node(state: AgentState) -> dict[str, Any]:
        proposal = evaluate_fn(state["question"], state.get("answer") or "")
        if proposal is None:
            return {}

        answer = state.get("answer") or ""
        question_for_user = f"\n\n¿Querés que recuerde esto para la próxima? {proposal.reason}"
        return {
            "pending_memory_proposal": proposal.model_dump(),
            "answer": answer + question_for_user,
        }

    return propose_memory_node


def _route_after_input_guard(state: AgentState) -> str:
    if not state["question"]:
        return "empty_question"
    if state.get("guardrail_blocked"):
        return "guardrail_blocked"
    if state.get("pending_memory_proposal"):
        return "resolve_pending_memory_proposal"
    return "classify_intent"


def _route_after_classify(state: AgentState) -> str:
    return "incidents_tool" if state["route"] == "both" else state["route"]


def _route_after_incidents_tool(state: AgentState) -> str:
    if state.get("route") == "both":
        return "retrieve"
    tool_result = state.get("tool_result") or {}
    return "generate" if tool_result.get("ok") else "tool_failed"


def _route_after_inventory_tool(state: AgentState) -> str:
    tool_result = state.get("tool_result") or {}
    return "generate" if tool_result.get("ok") else "tool_failed"


def _route_after_retrieve(state: AgentState) -> str:
    context = state.get("context") or []
    memory_context = state.get("memory_context") or []
    tool_result = state.get("tool_result")
    tool_ok = bool(tool_result and tool_result.get("ok"))
    return "no_context" if (not context and not memory_context and not tool_ok) else "generate"


def _default_generate_with_agent_prompt(question: str, context: list[dict[str, Any]]) -> str:
    """Default de `generate_fn` -- inyecta `AGENT_SYSTEM_PROMPT`
    (`guardrails.py`, Hito 8 Parte 2) en vez del `SYSTEM_PROMPT` genérico
    de `data/pipelines/rag.py` (ese es para `POST /knowledge/query`, una
    herramienta distinta con su propia audiencia)."""

    return generate_answer(question, context, system_prompt=AGENT_SYSTEM_PROMPT)


def build_graph(
    retrieve_fn: Callable[[str], list[dict[str, Any]]] = retrieve,
    generate_fn: Callable[[str, list[dict[str, Any]]], str] = _default_generate_with_agent_prompt,
    classify_fn: Callable[[str], str] = classify_intent,
    incidents_tool_fn: Callable[[dict[str, Any]], Any] = _default_incidents_tool_call,
    inventory_tool_fn: Callable[[dict[str, Any]], Any] = _default_inventory_tool_call,
    read_memory_fn: Callable[[str], Any] = _default_read_memory,
    evaluate_memory_fn: Callable[[str, str], MemoryProposal | None] = evaluate_for_memory_proposal,
    decide_memory_fn: Callable[[str], MemoryDecision] = classify_memory_decision,
    write_memory_fn: Callable[[str, str, str, str], None] = _default_write_memory,
    audit_memory_fn: Callable[..., None] = _default_record_memory_decision,
    sanitize_external_content_fn: Callable[[list[dict[str, Any]]], tuple[list[dict[str, Any]], bool]] = sanitize_external_content,
    validate_output_fn: Callable[[str], GuardrailResult | None] = validate_output,
    guardrail_audit_fn: Callable[..., None] = record_guardrail_event,
    checkpointer: Any = None,
) -> CompiledStateGraph:
    """Arma y compila el grafo. Todas las funciones de negocio son
    inyectables para poder probar el enrutamiento y el contrato de nodos
    sin credenciales reales de Qdrant/4Geeks ni un backend HTTP en vivo
    (ver `tests/pipelines/test_agent_graph.py`), sin Redis real para la
    memoria (ver `tests/pipelines/test_agent_memory.py`), y sin tocar los
    archivos reales de auditoría de guardrails (ver
    `tests/pipelines/test_agent_guardrails.py`).

    `.compile()` valida la estructura del grafo y lanza una excepción clara
    si algo está mal -- no se envuelve en un try/except que la esconda.
    """
    graph = StateGraph(AgentState)

    graph.add_node("receive_question", _receive_question_node)
    graph.add_node("input_guard", _make_input_guard_node(guardrail_audit_fn))
    graph.add_node("guardrail_blocked", _guardrail_blocked_node)
    graph.add_node(
        "resolve_pending_memory_proposal",
        _make_resolve_pending_memory_proposal_node(decide_memory_fn, write_memory_fn, audit_memory_fn),
    )
    graph.add_node("classify_intent", _make_classify_node(classify_fn))
    graph.add_node("retrieve_memory", _make_retrieve_memory_node(read_memory_fn))
    graph.add_node("retrieve", _make_retrieve_node(retrieve_fn))
    graph.add_node("incidents_tool", _make_incidents_tool_node(incidents_tool_fn))
    graph.add_node("inventory_tool", _make_inventory_tool_node(inventory_tool_fn))
    graph.add_node("generate", _make_generate_node(generate_fn, sanitize_external_content_fn, guardrail_audit_fn))
    graph.add_node("no_context", _no_context_node)
    graph.add_node("empty_question", _empty_question_node)
    graph.add_node("tool_failed", _tool_failed_node)
    graph.add_node("output_guard", _make_output_guard_node(validate_output_fn, guardrail_audit_fn))
    graph.add_node("propose_memory", _make_propose_memory_node(evaluate_memory_fn))

    graph.add_edge(START, "receive_question")
    graph.add_edge("receive_question", "input_guard")
    graph.add_conditional_edges(
        "input_guard",
        _route_after_input_guard,
        {
            "empty_question": "empty_question",
            "guardrail_blocked": "guardrail_blocked",
            "resolve_pending_memory_proposal": "resolve_pending_memory_proposal",
            "classify_intent": "classify_intent",
        },
    )
    graph.add_edge("resolve_pending_memory_proposal", "classify_intent")
    graph.add_edge("classify_intent", "retrieve_memory")
    graph.add_conditional_edges(
        "retrieve_memory",
        _route_after_classify,
        {"rag": "retrieve", "incidents_tool": "incidents_tool", "inventory_tool": "inventory_tool"},
    )
    graph.add_conditional_edges(
        "incidents_tool",
        _route_after_incidents_tool,
        {"retrieve": "retrieve", "generate": "generate", "tool_failed": "tool_failed"},
    )
    graph.add_conditional_edges(
        "inventory_tool",
        _route_after_inventory_tool,
        {"generate": "generate", "tool_failed": "tool_failed"},
    )
    graph.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {"no_context": "no_context", "generate": "generate"},
    )
    graph.add_edge("generate", "output_guard")
    graph.add_edge("no_context", "output_guard")
    graph.add_edge("output_guard", "propose_memory")
    graph.add_edge("propose_memory", END)
    graph.add_edge("guardrail_blocked", END)
    graph.add_edge("empty_question", END)
    graph.add_edge("tool_failed", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())


def _save_trace(thread_id: str, trace: list[dict[str, Any]]) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{thread_id}.json"
    path.write_text(json.dumps(trace, indent=2, ensure_ascii=False, default=str))
    return path


def get_trace(thread_id: str) -> list[dict[str, Any]] | None:
    """Lee el trace de una corrida ya terminada. `None` si no existe."""
    path = TRACE_DIR / f"{thread_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


async def run_agent(
    question: str,
    *,
    thread_id: str | None = None,
    authorized_order_ids: list[str] | None = None,
    retrieve_fn: Callable[[str], list[dict[str, Any]]] = retrieve,
    generate_fn: Callable[[str, list[dict[str, Any]]], str] = _default_generate_with_agent_prompt,
    classify_fn: Callable[[str], str] = classify_intent,
    incidents_tool_fn: Callable[[dict[str, Any]], Any] = _default_incidents_tool_call,
    inventory_tool_fn: Callable[[dict[str, Any]], Any] = _default_inventory_tool_call,
    read_memory_fn: Callable[[str], Any] = _default_read_memory,
    evaluate_memory_fn: Callable[[str, str], MemoryProposal | None] = evaluate_for_memory_proposal,
    decide_memory_fn: Callable[[str], MemoryDecision] = classify_memory_decision,
    write_memory_fn: Callable[[str, str, str, str], None] = _default_write_memory,
    audit_memory_fn: Callable[..., None] = _default_record_memory_decision,
    sanitize_external_content_fn: Callable[[list[dict[str, Any]]], tuple[list[dict[str, Any]], bool]] = sanitize_external_content,
    validate_output_fn: Callable[[str], GuardrailResult | None] = validate_output,
    guardrail_audit_fn: Callable[..., None] = record_guardrail_event,
    checkpointer: Any = None,
) -> tuple[AgentState, list[dict[str, Any]], str]:
    """Corre el grafo de punta a punta. Devuelve `(estado_final, trace, thread_id)`.

    `async def` porque `incidents_tool`/`inventory_tool` llaman al MCP
    Server vía `langchain-mcp-adapters` (async) -- ver docstring del módulo,
    "Migración a MCP".

    `thread_id` importa más que antes (Hito 8): `pending_memory_proposal`
    solo sobrevive al turno siguiente si el caller reutiliza el MISMO
    `thread_id` -- ver `_DEFAULT_CHECKPOINTER`, compartido entre llamadas
    para que esto funcione a través de requests HTTP separados.

    `authorized_order_ids` (Hito 8 Parte 2): los números de pedido/tracking
    que la sesión que llama puede consultar legítimamente -- ver
    `guardrails.py::check_unauthorized_tracking_request` y
    `Pasos/agent-guardrails.md`, "Decisiones", sobre el límite real de no
    tener un sistema de autenticación de sesión conectado a este endpoint
    todavía (`None` desactiva este guardrail en vez de bloquear todo).

    El trace es la secuencia real `[{"node": ..., "output": ...}, ...]` en
    el orden en que LangGraph ejecutó los nodos (`stream_mode="updates"`),
    guardada en disco para poder consultarla después de la corrida — y
    muestra con claridad si se usó el RAG, una tool, o ambos.
    """
    compiled_graph = build_graph(
        retrieve_fn=retrieve_fn,
        generate_fn=generate_fn,
        classify_fn=classify_fn,
        incidents_tool_fn=incidents_tool_fn,
        inventory_tool_fn=inventory_tool_fn,
        read_memory_fn=read_memory_fn,
        evaluate_memory_fn=evaluate_memory_fn,
        decide_memory_fn=decide_memory_fn,
        write_memory_fn=write_memory_fn,
        audit_memory_fn=audit_memory_fn,
        sanitize_external_content_fn=sanitize_external_content_fn,
        validate_output_fn=validate_output_fn,
        guardrail_audit_fn=guardrail_audit_fn,
        checkpointer=checkpointer or _DEFAULT_CHECKPOINTER,
    )
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    trace: list[dict[str, Any]] = []
    final_state: dict[str, Any] = {"question": question, "thread_id": thread_id}

    async for update in compiled_graph.astream(
        {"question": question, "thread_id": thread_id, "authorized_order_ids": authorized_order_ids},
        config=config,
        stream_mode="updates",
    ):
        for node_name, partial_state in update.items():
            # LangGraph representa un nodo que no cambio nada del estado
            # (p. ej. `propose_memory` cuando no hay nada memorable, que
            # devuelve `{}`) como `None` en el stream de "updates" -- no es
            # un error, es "sin cambios" (descubierto corriendo este
            # escenario, ver Pasos/).
            partial_state = partial_state or {}
            trace.append({"node": node_name, "output": partial_state})
            final_state.update(partial_state)

    _save_trace(thread_id, trace)
    return final_state, trace, thread_id  # type: ignore[return-value]
