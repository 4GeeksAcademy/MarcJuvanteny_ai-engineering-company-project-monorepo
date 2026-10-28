"""Pruebas del endpoint SSE `GET /rfp/events` (`CONTEXT/CONTEXT10.md`,
checklist "Pruebas"): se prueba el endpoint en sí, por HTTP (TestClient),
con un JWT real emitido por `auth_service.create_access_token` -- se
afirman los headers de respuesta, el framing del wire (`id:` / `event:
rfp_ticket_created` / `data:` JSON) y la forma exacta del payload, no un
dict suelto desligado del framing.

El outbox vive en SQLite (archivo temporal, no hace falta Postgres): solo se crean
`rfp_tickets` y `rfp_ticket_events` -- `rfp_metadata` usa JSONB, que SQLite
no compila, y el endpoint nunca la lee (el payload ya es un snapshot).

Correr con el venv del servicio:

    cd services/incidents-api
    uv run --group dev pytest ../../tests/services -q
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT_DIR / "services" / "incidents-api"
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

# Antes de importar el servicio: `database.py` crea su motor al importarse y
# `auth_service` firma con JWT_SECRET_KEY. `setdefault` nunca pisa un .env real.
os.environ.setdefault("SUPABASE_DATABASE_URL", "sqlite://")
os.environ["JWT_SECRET_KEY"] = "test-secret-rfp-events-32-bytes-min"
os.environ["TINYDB_PATH"] = str(Path(tempfile.mkdtemp()) / "users.json")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from auth_service import create_access_token  # noqa: E402
from database import get_tinydb_path  # noqa: E402
from models import UserRegister  # noqa: E402
from routers.rfp_events import (  # noqa: E402
    StreamSettings,
    get_rfp_events_engine,
    get_stream_settings,
    router,
)
from rfp_intake.events import RFP_TICKET_CREATED, RFPTicketEvent, record_ticket_created  # noqa: E402
from rfp_intake.models import RFPMetadataRecord, RFPTicket, TicketStatus  # noqa: E402
from user_service import create_user  # noqa: E402

EXPECTED_PAYLOAD_KEYS = {
    "ticket_id",
    "rfp_id",
    "client_name",
    "client_country",
    "services_requested",
    "status",
    "created_at",
}


@pytest.fixture()
def engine(tmp_path):
    # SQLite en archivo (no `:memory:` + StaticPool): el servidor uvicorn de
    # los tests en vivo corre en otro hilo, y con UNA conexión compartida el
    # rollback de su sesión deshacía la transacción del test. Con archivo,
    # cada sesión tiene su conexión -- igual que contra Postgres.
    engine = create_engine(f"sqlite:///{tmp_path / 'rfp_events.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine, tables=[RFPTicket.__table__, RFPTicketEvent.__table__])
    return engine


@pytest.fixture()
def settings_holder():
    return {"settings": StreamSettings(poll_interval_seconds=0.01, keepalive_seconds=60, max_polls=2)}


@pytest.fixture()
def client(engine, settings_holder):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_rfp_events_engine] = lambda: engine
    app.dependency_overrides[get_stream_settings] = lambda: settings_holder["settings"]
    return TestClient(app)


@pytest.fixture(scope="module")
def token() -> str:
    user = create_user(
        get_tinydb_path(),
        UserRegister(email="ventas.sse@trackflow.test", password="Sup3rSecret!", name="Ventas SSE"),
    )
    access_token, _ = create_access_token(user.id, str(user.role))
    return access_token


def _auth(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _insert_ticket_created(engine, *, client_name: str = "Northline Apparel") -> RFPTicketEvent:
    """Mismo camino que el pipeline real: ticket en `analizando` + metadata
    -> `record_ticket_created` (outbox). La metadata no se persiste (JSONB,
    ver docstring), solo se le asigna el id que tendría como `rfp_id`."""

    with Session(engine) as session:
        ticket = RFPTicket(
            status=TicketStatus.ANALIZANDO.value,
            raw_pdf_path="/tmp/rfp.pdf",
            created_at=datetime(2026, 7, 24, 14, 32, tzinfo=timezone.utc),
        )
        session.add(ticket)
        session.flush()
        metadata = RFPMetadataRecord(
            id=ticket.id + 100,
            ticket_id=ticket.id,
            client_name=client_name,
            client_country="USA",
            services_requested=["warehouse", "lastmile"],
        )
        event = record_ticket_created(session, ticket, metadata)
        session.commit()
        session.refresh(event)
        session.expunge(event)
        return event


def _parse_sse(body: str) -> list[dict[str, str]]:
    """Parser mínimo del wire SSE: frames separados por línea en blanco;
    los comentarios (`: ...`) se guardan bajo la clave "comment"."""

    frames: list[dict[str, str]] = []
    for raw_frame in body.split("\n\n"):
        if not raw_frame.strip():
            continue
        frame: dict[str, str] = {}
        for line in raw_frame.split("\n"):
            if line.startswith(":"):
                frame["comment"] = frame.get("comment", "") + line[1:].strip()
                continue
            field, _, value = line.partition(":")
            frame[field] = value[1:] if value.startswith(" ") else value
        frames.append(frame)
    return frames


def _event_frames(body: str) -> list[dict[str, str]]:
    return [frame for frame in _parse_sse(body) if "event" in frame]


# --- autenticación ---------------------------------------------------------------------


def test_stream_rejects_requests_without_jwt(client):
    response = client.get("/rfp/events")

    assert response.status_code == 401
    assert "text/event-stream" not in response.headers.get("content-type", "")


def test_stream_rejects_an_invalid_jwt(client):
    response = client.get("/rfp/events", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


# --- headers + framing + payload ---------------------------------------------------------


def test_stream_headers_and_named_event_wire_format(client, engine, token):
    created = _insert_ticket_created(engine)

    response = client.get("/rfp/events", headers=_auth(token, **{"Last-Event-ID": "0"}))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    # Wire literal: `id:` + `event:` con nombre + `data:` JSON en ese orden.
    assert f"id: {created.id}\nevent: rfp_ticket_created\ndata: {{" in response.text
    assert "event: message" not in response.text

    frames = _event_frames(response.text)
    assert len(frames) == 1
    frame = frames[0]
    assert frame["event"] == RFP_TICKET_CREATED
    assert frame["id"] == str(created.id)

    payload = json.loads(frame["data"])
    # Solo campos del ticket, sin sobre anidado {"event","data"} (CONTEXT10.md §3).
    assert set(payload) == EXPECTED_PAYLOAD_KEYS
    assert payload["ticket_id"] == created.ticket_id
    assert payload["rfp_id"] == created.ticket_id + 100
    assert payload["client_name"] == "Northline Apparel"
    assert payload["client_country"] == "USA"
    assert payload["services_requested"] == ["warehouse", "lastmile"]
    assert payload["status"] == "analizando"
    assert payload["created_at"] == "2026-07-24T14:32:00Z"


def test_stream_announces_retry_and_sends_keepalive_comments_when_idle(client, settings_holder, token):
    settings_holder["settings"] = StreamSettings(poll_interval_seconds=0.01, keepalive_seconds=0, max_polls=3)

    response = client.get("/rfp/events", headers=_auth(token))

    assert response.status_code == 200
    assert response.text.startswith("retry: ")
    assert ": keep-alive\n\n" in response.text
    assert _event_frames(response.text) == []


# --- replay / Last-Event-ID ------------------------------------------------------------


def test_new_connection_without_last_event_id_starts_at_now_and_hands_out_the_cursor(client, engine, token):
    """Lo anterior lo carga la UI con GET /rfp/tickets; el stream no lo
    repite -- pero el frame de apertura le da al cliente el cursor actual
    (`id:` sin `data:`) para que un reconnect posterior pueda hacer replay
    aunque nunca haya recibido un evento."""

    existing = _insert_ticket_created(engine)

    response = client.get("/rfp/events", headers=_auth(token))

    assert _event_frames(response.text) == []
    opening = _parse_sse(response.text)[0]
    assert opening["id"] == str(existing.id)
    assert "data" not in opening


def test_reconnect_with_last_event_id_replays_only_missed_events(client, engine, token):
    first = _insert_ticket_created(engine, client_name="ModaViva")
    second = _insert_ticket_created(engine, client_name="Luna Cosmetics")
    third = _insert_ticket_created(engine, client_name="Northline Apparel")

    response = client.get("/rfp/events", headers=_auth(token, **{"Last-Event-ID": str(first.id)}))

    frames = _event_frames(response.text)
    assert [frame["id"] for frame in frames] == [str(second.id), str(third.id)]
    assert [json.loads(frame["data"])["client_name"] for frame in frames] == ["Luna Cosmetics", "Northline Apparel"]


def test_garbage_last_event_id_is_treated_as_a_new_connection(client, engine, token):
    _insert_ticket_created(engine)

    response = client.get("/rfp/events", headers=_auth(token, **{"Last-Event-ID": "abc"}))

    assert response.status_code == 200
    assert _event_frames(response.text) == []


# --- entrega en vivo ---------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _start_server(engine, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    """uvicorn real en un hilo: el TestClient de Starlette bufferiza la
    respuesta completa antes de devolverla, así que no puede probar que un
    evento llegue MIENTRAS la conexión sigue abierta, ni una caída real."""

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_rfp_events_engine] = lambda: engine
    app.dependency_overrides[get_stream_settings] = lambda: StreamSettings(
        poll_interval_seconds=0.02, keepalive_seconds=60, max_polls=500
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn no arrancó"
    return server, thread


def _stop_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    server.force_exit = True  # no esperar a que cierren los streams abiertos
    thread.join(timeout=5)


@pytest.fixture()
def live_server_url(engine):
    port = _free_port()
    server, thread = _start_server(engine, port)
    yield f"http://127.0.0.1:{port}"
    _stop_server(server, thread)


def test_event_recorded_while_connected_is_pushed_live(live_server_url, engine, token):
    received = ""
    with httpx.stream("GET", f"{live_server_url}/rfp/events", headers=_auth(token), timeout=5) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        inserted = False
        for chunk in response.iter_text():
            received += chunk
            if not inserted and ": connected" in received:
                # El stream ya está abierto y sin eventos -- recién ahora el
                # "worker" registra el ticket.
                assert _event_frames(received) == []
                created = _insert_ticket_created(engine, client_name="Live Client")
                inserted = True
            if "event: rfp_ticket_created" in received and received.endswith("\n\n"):
                break

    frames = _event_frames(received)
    assert len(frames) == 1
    assert frames[0]["id"] == str(created.id)
    assert json.loads(frames[0]["data"])["client_name"] == "Live Client"


# --- caída + reconexión con backoff + recuperación ---------------------------------------


def test_reconnect_after_server_crash_uses_backoff_and_recovers_missed_tickets_without_duplicates(engine, token):
    """Mismo protocolo que `uis/backoffice/src/lib/use-rfp-ticket-stream.ts`:
    guarda el último `id:` (incluido el del frame de apertura), reintenta con
    backoff exponencial mientras el servidor está caído, reconecta con
    `Last-Event-ID` y deduplica por `ticket_id` antes de "pintar"."""

    port = _free_port()
    url = f"http://127.0.0.1:{port}/rfp/events"
    before = _insert_ticket_created(engine, client_name="Ya en la lista")
    known_ticket_ids = {before.ticket_id}  # lo que trajo GET /rfp/tickets al cargar
    displayed: list[int] = []
    last_event_id: str | None = None

    def consume(text: str) -> None:
        nonlocal last_event_id
        for frame in _parse_sse(text):
            if "id" in frame:
                last_event_id = frame["id"]
            if frame.get("event") != RFP_TICKET_CREATED:
                continue
            ticket_id = json.loads(frame["data"])["ticket_id"]
            if ticket_id in known_ticket_ids:
                continue
            known_ticket_ids.add(ticket_id)
            displayed.append(ticket_id)

    # 1) Conectado: recibe el cursor y un ticket en vivo.
    server, thread = _start_server(engine, port)
    received = ""
    with httpx.stream("GET", url, headers=_auth(token), timeout=5) as response:
        live = None
        for chunk in response.iter_text():
            received += chunk
            if live is None and ": connected" in received:
                live = _insert_ticket_created(engine, client_name="En vivo")
            if "event: rfp_ticket_created" in received and received.endswith("\n\n"):
                break
    consume(received)
    assert displayed == [live.ticket_id]
    assert last_event_id == str(live.id)

    # 2) Caída del servidor. Mientras está abajo entran 2 tickets; uno de
    #    ellos la UI ya lo conocía (p. ej. lo subió esta misma pestaña).
    _stop_server(server, thread)
    missed_known = _insert_ticket_created(engine, client_name="Subido por mí")
    missed_new = _insert_ticket_created(engine, client_name="Llegó durante la caída")
    known_ticket_ids.add(missed_known.ticket_id)

    # 3) Reconexión con backoff progresivo; el servidor vuelve a los ~0.35s.
    restarted: dict[str, object] = {}
    restart_timer = threading.Timer(
        0.35, lambda: restarted.update(zip(("server", "thread"), _start_server(engine, port)))
    )
    restart_timer.start()

    delays: list[float] = []
    received = ""
    try:
        while True:
            try:
                with httpx.stream(
                    "GET", url, headers=_auth(token, **{"Last-Event-ID": last_event_id}), timeout=5
                ) as response:
                    assert response.status_code == 200
                    for chunk in response.iter_text():
                        received += chunk
                        if received.count("event: rfp_ticket_created") == 2 and received.endswith("\n\n"):
                            break
                break
            except httpx.TransportError:
                delay = min(1.0, 0.05 * 2 ** len(delays))
                delays.append(delay)
                assert len(delays) < 10, "el servidor nunca volvió"
                time.sleep(delay)
    finally:
        restart_timer.join()
        if "server" in restarted:
            _stop_server(restarted["server"], restarted["thread"])

    consume(received)

    assert len(delays) >= 2, "el backoff debía dispararse al menos dos veces con el servidor caído"
    assert delays == sorted(delays) and delays[0] < delays[-1]
    # Replay exacto: los 2 eventos perdidos y nada anterior al Last-Event-ID.
    replayed_ids = [frame["id"] for frame in _event_frames(received)]
    assert replayed_ids == [str(missed_known.id), str(missed_new.id)]
    # Recuperado el que faltaba, sin duplicar el que la UI ya tenía.
    assert displayed == [live.ticket_id, missed_new.ticket_id]
    assert len(displayed) == len(set(displayed))


# --- outbox ------------------------------------------------------------------------------


def test_record_ticket_created_is_idempotent_per_ticket(engine):
    first = _insert_ticket_created(engine)

    with Session(engine) as session:
        ticket = session.get(RFPTicket, first.ticket_id)
        metadata = RFPMetadataRecord(id=999, ticket_id=ticket.id, client_name="otra vez")
        again = record_ticket_created(session, ticket, metadata)
        session.commit()

        assert again.id == first.id
        assert len(session.exec(select(RFPTicketEvent)).all()) == 1
