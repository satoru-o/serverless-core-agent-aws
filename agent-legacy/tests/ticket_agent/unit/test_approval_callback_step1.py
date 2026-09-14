from unittest.mock import patch


def _event(token: str, decision: str) -> dict:
    return {"path": "/approvals", "queryStringParameters": {"token": token, "decision": decision}}


@patch("ticket_agent.approval_callback_handler._sfn")
@patch("ticket_agent.approval_callback_handler.approval_links")
def test_step1_marks_consumed_and_never_calls_step_functions(mock_links, mock_sfn):
    from ticket_agent.approval_callback_handler import lambda_handler

    mock_links.get.return_value = None

    response = lambda_handler(_event("tok-1", "approve"), None)

    mock_links.mark_consumed.assert_called_once_with("tok-1", "approve")
    mock_sfn.send_task_success.assert_not_called()
    mock_sfn.send_task_failure.assert_not_called()
    assert response["statusCode"] == 200
    assert "承認" in response["body"]


@patch("ticket_agent.approval_callback_handler._sfn")
@patch("ticket_agent.approval_callback_handler.approval_links")
def test_step1_shows_already_processed_when_confirmed(mock_links, mock_sfn):
    from ticket_agent.approval_callback_handler import lambda_handler

    mock_links.get.return_value = {
        "task_token": "tok-1",
        "confirmed_at": "2026-01-01T00:00:00+00:00",
    }

    response = lambda_handler(_event("tok-1", "approve"), None)

    mock_links.mark_consumed.assert_not_called()
    mock_sfn.send_task_success.assert_not_called()
    mock_sfn.send_task_failure.assert_not_called()
    assert "既に処理済み" in response["body"]


def test_missing_token_returns_400():
    from ticket_agent.approval_callback_handler import lambda_handler

    event = {"path": "/approvals", "queryStringParameters": {"decision": "approve"}}
    response = lambda_handler(event, None)

    assert response["statusCode"] == 400


def test_invalid_decision_value_returns_400():
    from ticket_agent.approval_callback_handler import lambda_handler

    response = lambda_handler(_event("tok-1", "delete"), None)

    assert response["statusCode"] == 400
