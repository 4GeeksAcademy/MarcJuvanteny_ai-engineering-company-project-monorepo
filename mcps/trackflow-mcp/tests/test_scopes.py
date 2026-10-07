"""Tests de `scopes.py`: minimo privilegio por-tool."""

from __future__ import annotations

import pytest
from mcpauth.types import AuthInfo

import scopes


class _FakeMcpAuth:
    def __init__(self, auth_info: AuthInfo | None):
        self._auth_info = auth_info

    @property
    def auth_info(self) -> AuthInfo | None:
        return self._auth_info


def _auth_info(scope_list: list[str]) -> AuthInfo:
    return AuthInfo(token="t", issuer="https://issuer.test", subject="sub", scopes=scope_list, claims={})


def test_require_scope_passes_when_scope_present():
    scopes.configure(_FakeMcpAuth(_auth_info(["incidents:read", "mcp:access"])))
    scopes.require_scope("incidents:read")  # no debe levantar


def test_require_scope_raises_scope_error_when_missing():
    scopes.configure(_FakeMcpAuth(_auth_info(["mcp:access"])))

    with pytest.raises(scopes.ScopeError) as excinfo:
        scopes.require_scope("incidents:write")

    assert excinfo.value.code == "missing_required_scope"
    assert excinfo.value.required_scope == "incidents:write"
    assert "missing_required_scope" in str(excinfo.value)


def test_require_scope_raises_when_no_auth_info_at_all():
    scopes.configure(_FakeMcpAuth(None))

    with pytest.raises(scopes.ScopeError):
        scopes.require_scope("incidents:read")


def test_require_scope_before_configure_is_a_startup_bug_not_a_scope_error():
    scopes._mcp_auth = None  # reset explicito, simula arranque incompleto

    with pytest.raises(RuntimeError):
        scopes.require_scope("incidents:read")
