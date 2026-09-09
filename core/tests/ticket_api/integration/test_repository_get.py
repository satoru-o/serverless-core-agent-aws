import pytest
from ticket_api import repository
from ticket_api.errors import NotFoundError


def test_get_ticket_returns_created_ticket():
    created = repository.create_ticket(title="A", description="説明", assignee="x")

    fetched = repository.get_ticket(created.ticket_id)

    assert fetched == created


def test_get_ticket_raises_not_found_for_unknown_id():
    with pytest.raises(NotFoundError):
        repository.get_ticket("00000000-0000-0000-0000-000000000000")
