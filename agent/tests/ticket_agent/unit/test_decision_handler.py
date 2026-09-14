from unittest.mock import patch

from ticket_agent.decision_handler import lambda_handler


def _ticket(ticket_id: str) -> dict:
    return {"ticket_id": ticket_id, "status": "OPEN"}


@patch.dict("os.environ", {"TICKET_API_BASE_URL": "https://example.com/v1", "EXECUTION_LIMIT": "3"})
@patch("ticket_agent.decision_handler.decide")
@patch("ticket_agent.decision_handler.TicketClient")
def test_stops_at_execution_limit_and_logs(mock_ticket_client_cls, mock_decide, capsys):
    client = mock_ticket_client_cls.return_value
    # OPEN一覧・IN_PROGRESS一覧の呼び出しでcall_countが2になり、
    # 1件目のupdate_status呼び出しが3回目(上限内)、2件目が4回目(上限超過)になる想定
    client.list_tickets.side_effect = lambda status: (
        [_ticket("t1"), _ticket("t2")] if status == "OPEN" else []
    )
    mock_decide.return_value = "START_PROGRESS"

    result = lambda_handler({}, None)

    assert result["outcome"] == "limit_reached"
    assert result["processed"] == 1
    assert client.update_status.call_count == 1
    client.update_status.assert_called_once_with("t1", "IN_PROGRESS")

    logs = [line for line in capsys.readouterr().out.splitlines() if line]
    limit_logs = [json_line for json_line in logs if "EXECUTION_LIMIT_REACHED" in json_line]
    assert len(limit_logs) == 1


@patch.dict("os.environ", {"TICKET_API_BASE_URL": "https://example.com/v1", "EXECUTION_LIMIT": "20"})
@patch("ticket_agent.decision_handler.decide")
@patch("ticket_agent.decision_handler.TicketClient")
def test_processes_all_tickets_within_limit(mock_ticket_client_cls, mock_decide, capsys):
    client = mock_ticket_client_cls.return_value
    client.list_tickets.side_effect = lambda status: (
        [_ticket("t1")] if status == "OPEN" else []
    )
    mock_decide.return_value = "START_PROGRESS"

    result = lambda_handler({}, None)

    assert result == {"processed": 1, "outcome": "completed"}
    client.update_status.assert_called_once_with("t1", "IN_PROGRESS")

    logs = capsys.readouterr().out
    assert "TRANSITION_IN_PROGRESS" in logs


@patch.dict("os.environ", {"TICKET_API_BASE_URL": "https://example.com/v1", "EXECUTION_LIMIT": "20"})
@patch("ticket_agent.decision_handler.decide")
@patch("ticket_agent.decision_handler.TicketClient")
def test_no_op_decision_does_not_call_update_status(mock_ticket_client_cls, mock_decide):
    client = mock_ticket_client_cls.return_value
    client.list_tickets.side_effect = lambda status: (
        [_ticket("t1")] if status == "IN_PROGRESS" else []
    )
    mock_decide.return_value = "NO_OP"

    result = lambda_handler({}, None)

    assert result == {"processed": 1, "outcome": "completed"}
    client.update_status.assert_not_called()
