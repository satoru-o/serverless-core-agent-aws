from ticket_api import repository


def test_list_tickets_without_filter_returns_all():
    a = repository.create_ticket(title="A", description="", assignee="x")
    b = repository.create_ticket(title="B", description="", assignee="y")
    repository.update_status(b.ticket_id, "IN_PROGRESS")

    tickets = repository.list_tickets()

    ids = {t.ticket_id for t in tickets}
    assert ids == {a.ticket_id, b.ticket_id}


def test_list_tickets_filtered_by_status():
    a = repository.create_ticket(title="A", description="", assignee="x")
    b = repository.create_ticket(title="B", description="", assignee="y")
    repository.update_status(b.ticket_id, "IN_PROGRESS")

    open_tickets = repository.list_tickets(status="OPEN")
    in_progress_tickets = repository.list_tickets(status="IN_PROGRESS")

    assert [t.ticket_id for t in open_tickets] == [a.ticket_id]
    assert [t.ticket_id for t in in_progress_tickets] == [b.ticket_id]


def test_list_tickets_returns_empty_list_when_none_exist():
    assert repository.list_tickets() == []
    assert repository.list_tickets(status="OPEN") == []
