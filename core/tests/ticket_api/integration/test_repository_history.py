import pytest
from ticket_api import repository
from ticket_api.errors import InvalidTransitionError, NotFoundError


def test_history_is_ordered_and_accurate():
    ticket = repository.create_ticket(title="A", description="", assignee="x")
    repository.update_status(ticket.ticket_id, "IN_PROGRESS")
    repository.update_status(ticket.ticket_id, "OPEN")
    repository.update_status(ticket.ticket_id, "IN_PROGRESS")
    repository.update_status(ticket.ticket_id, "DONE")

    history = repository.get_history(ticket.ticket_id)

    assert [h.to_status for h in history] == [
        "OPEN",
        "IN_PROGRESS",
        "OPEN",
        "IN_PROGRESS",
        "DONE",
    ]
    assert [h.from_status for h in history] == [
        None,
        "OPEN",
        "IN_PROGRESS",
        "OPEN",
        "IN_PROGRESS",
    ]
    # changed_at が発生順(昇順)になっていること
    changed_ats = [h.changed_at for h in history]
    assert changed_ats == sorted(changed_ats)


def test_rejected_transition_is_not_recorded_in_history():
    ticket = repository.create_ticket(title="A", description="", assignee="x")

    with pytest.raises(InvalidTransitionError):
        repository.update_status(ticket.ticket_id, "DONE")  # OPEN -> DONE は未定義

    history = repository.get_history(ticket.ticket_id)
    assert [h.to_status for h in history] == ["OPEN"]


def test_get_history_raises_not_found_for_unknown_ticket():
    with pytest.raises(NotFoundError):
        repository.get_history("00000000-0000-0000-0000-000000000000")
