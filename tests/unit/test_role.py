"""Role / write authority tests."""

from __future__ import annotations

from lumencast.protocol.types import Role
from lumencast.server.role import role_can_write


def test_operator_writes_inputs_only() -> None:
    assert role_can_write(Role.OPERATOR, "__inputs.title") is True
    assert role_can_write(Role.OPERATOR, "__test.sandbox") is False
    assert role_can_write(Role.OPERATOR, "freestyle.path") is False


def test_viewer_writes_nothing() -> None:
    assert role_can_write(Role.VIEWER, "__inputs.x") is False


def test_test_writes_test_only() -> None:
    assert role_can_write(Role.TEST, "__test.x") is True
    assert role_can_write(Role.TEST, "__inputs.x") is False


def test_service_unscoped_writes_inputs() -> None:
    assert role_can_write(Role.SERVICE, "__inputs.x") is True


def test_service_scoped_pattern_match() -> None:
    paths = ["__inputs.allowed.*"]
    assert role_can_write(Role.SERVICE, "__inputs.allowed.foo", paths=paths) is True
    assert role_can_write(Role.SERVICE, "__inputs.other", paths=paths) is False


def test_service_outside_inputs_namespace_denied() -> None:
    paths = ["something.*"]
    assert role_can_write(Role.SERVICE, "something.x", paths=paths) is False
