from unittest.mock import patch

from ticket_agent.apply_decision_handler import lambda_handler


@patch.dict("os.environ", {"TICKET_API_BASE_URL": "https://example.com/v1"})
@patch("ticket_agent.apply_decision_handler.TicketClient")
def test_transitions_ticket_to_done(mock_ticket_client_cls, capsys):
    client = mock_ticket_client_cls.return_value

    result = lambda_handler({"ticket_id": "abc"}, None)

    client.update_status.assert_called_once_with("abc", "DONE")
    assert result == {"ticket_id": "abc", "status": "DONE"}

    logs = capsys.readouterr().out
    assert "APPROVE" in logs
    assert "TRANSITION_DONE" in logs
