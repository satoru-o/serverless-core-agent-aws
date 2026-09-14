"""FR-011(重大操作の自動実行禁止)の振る舞いレベル検証(/speckit-analyze F4対応)。

IAM境界テスト(test_iam_boundaries_decision.py, test_iam_boundaries_approval.py)は
ロールの権限レベルでの担保を検証するのに対し、本テストは`decision_handler`のコード自身が
`COMPLETE`判断時に`ticket_client.update_status(..., "DONE")`を一切呼び出さないことを
直接検証する。
"""

import json
from unittest.mock import patch

from ticket_agent.decision_handler import lambda_handler


def _ticket(ticket_id: str) -> dict:
    return {"ticket_id": ticket_id, "status": "IN_PROGRESS"}


@patch.dict(
    "os.environ",
    {
        "TICKET_API_BASE_URL": "https://example.com/v1",
        "EXECUTION_LIMIT": "20",
        "APPROVAL_STATE_MACHINE_ARN": "arn:aws:states:ap-northeast-1:123456789012:stateMachine:agent-approval-flow",
    },
)
@patch("ticket_agent.decision_handler._sfn")
@patch("ticket_agent.decision_handler.decide")
@patch("ticket_agent.decision_handler.TicketClient")
def test_complete_decision_only_starts_approval_execution(
    mock_ticket_client_cls, mock_decide, mock_sfn, capsys
):
    client = mock_ticket_client_cls.return_value
    client.list_tickets.side_effect = lambda status: (
        [_ticket("t1")] if status == "IN_PROGRESS" else []
    )
    mock_decide.return_value = "COMPLETE"

    result = lambda_handler({}, None)

    # states.start_execution() のみが呼ばれ、Ticket APIのDONE遷移は一切呼ばれないこと
    mock_sfn.start_execution.assert_called_once()
    call_kwargs = mock_sfn.start_execution.call_args.kwargs
    assert call_kwargs["stateMachineArn"] == (
        "arn:aws:states:ap-northeast-1:123456789012:stateMachine:agent-approval-flow"
    )
    execution_input = json.loads(call_kwargs["input"])
    assert execution_input["ticket_id"] == "t1"
    assert execution_input["requested_action"] == "TRANSITION_DONE"

    client.update_status.assert_not_called()
    assert result == {"processed": 1, "outcome": "completed"}

    logs = capsys.readouterr().out
    assert "REQUEST_APPROVAL" in logs
    assert "TRANSITION_DONE" not in logs
