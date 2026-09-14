import json
from unittest.mock import patch

from ticket_agent.errors import UnauthorizedTicketApiCallError
from ticket_agent.decision_handler import lambda_handler


def _ticket(ticket_id: str) -> dict:
    return {"ticket_id": ticket_id, "status": "OPEN"}


@patch.dict(
    "os.environ",
    {"TICKET_API_BASE_URL": "https://example.com/v1", "EXECUTION_LIMIT": "20"},
)
@patch("ticket_agent.decision_handler.decide")
@patch("ticket_agent.decision_handler.TicketClient")
def test_unauthorized_call_is_logged_and_processing_continues(
    mock_ticket_client_cls, mock_decide, capsys
):
    client = mock_ticket_client_cls.return_value
    client.list_tickets.side_effect = lambda status: (
        [_ticket("t1"), _ticket("t2")] if status == "OPEN" else []
    )
    mock_decide.return_value = "START_PROGRESS"
    client.update_status.side_effect = UnauthorizedTicketApiCallError(
        "PATCH", "/tickets/t1/status"
    )

    result = lambda_handler({}, None)

    # 拒否されても処理自体はクラッシュせず継続する(残り1件も処理対象としてカウントする)
    assert result["outcome"] == "completed"
    assert result["processed"] == 2

    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    unauthorized_logs = [record for record in logs if record["action"] == "UNAUTHORIZED_ATTEMPT"]
    assert len(unauthorized_logs) == 2
    assert unauthorized_logs[0]["result"] == "rejected"
    assert unauthorized_logs[0]["ticket_id"] == "t1"
