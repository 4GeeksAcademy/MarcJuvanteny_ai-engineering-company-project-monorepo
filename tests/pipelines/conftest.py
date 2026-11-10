from __future__ import annotations

import pytest


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _agent_decision_log_to_tmp(monkeypatch, tmp_path):
    """Hito 12: `run_agent` escribe un registro de decisiones (JSONL); en
    tests va a un temporal, nunca a data/eval/ del repo."""

    monkeypatch.setenv("AGENT_DECISION_LOG_PATH", str(tmp_path / "agent-decision-log.jsonl"))
