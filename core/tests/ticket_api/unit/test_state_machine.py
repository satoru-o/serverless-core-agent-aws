import pytest
from ticket_api.state_machine import is_valid_transition

ALLOWED = [
    ("OPEN", "IN_PROGRESS"),
    ("IN_PROGRESS", "DONE"),
    ("IN_PROGRESS", "OPEN"),
]

FORBIDDEN = [
    ("DONE", "OPEN"),
    ("DONE", "IN_PROGRESS"),
    ("OPEN", "DONE"),
    ("OPEN", "OPEN"),
    ("IN_PROGRESS", "IN_PROGRESS"),
    ("DONE", "DONE"),
]


@pytest.mark.parametrize("from_status,to_status", ALLOWED)
def test_allowed_transitions(from_status, to_status):
    assert is_valid_transition(from_status, to_status) is True


@pytest.mark.parametrize("from_status,to_status", FORBIDDEN)
def test_forbidden_transitions(from_status, to_status):
    assert is_valid_transition(from_status, to_status) is False
