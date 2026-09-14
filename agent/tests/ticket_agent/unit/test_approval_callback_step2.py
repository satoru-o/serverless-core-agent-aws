from unittest.mock import patch


def _event(token: str, decision: str) -> dict:
    return {
        "path": "/approvals/confirm",
        "queryStringParameters": {"token": token, "decision": decision},
    }


@patch("ticket_agent.approval_callback_handler._sfn")
@patch("ticket_agent.approval_callback_handler.approval_links")
def test_step2_sends_task_success_for_approve(mock_links, mock_sfn):
    from ticket_agent.approval_callback_handler import lambda_handler

    mock_links.mark_confirmed.return_value = True

    response = lambda_handler(_event("tok-1", "approve"), None)

    mock_links.mark_confirmed.assert_called_once_with("tok-1")
    mock_sfn.send_task_success.assert_called_once()
    assert mock_sfn.send_task_success.call_args.kwargs["taskToken"] == "tok-1"
    mock_sfn.send_task_failure.assert_not_called()
    assert response["statusCode"] == 200


@patch("ticket_agent.approval_callback_handler._sfn")
@patch("ticket_agent.approval_callback_handler.approval_links")
def test_step2_sends_task_failure_for_reject(mock_links, mock_sfn):
    from ticket_agent.approval_callback_handler import lambda_handler

    mock_links.mark_confirmed.return_value = True

    lambda_handler(_event("tok-1", "reject"), None)

    mock_sfn.send_task_failure.assert_called_once()
    kwargs = mock_sfn.send_task_failure.call_args.kwargs
    assert kwargs["taskToken"] == "tok-1"
    assert kwargs["error"] == "Rejected"
    mock_sfn.send_task_success.assert_not_called()


@patch("ticket_agent.approval_callback_handler._sfn")
@patch("ticket_agent.approval_callback_handler.approval_links")
def test_step2_does_not_resend_when_already_confirmed(mock_links, mock_sfn):
    from ticket_agent.approval_callback_handler import lambda_handler

    mock_links.mark_confirmed.return_value = False

    response = lambda_handler(_event("tok-1", "approve"), None)

    mock_sfn.send_task_success.assert_not_called()
    mock_sfn.send_task_failure.assert_not_called()
    assert response["statusCode"] == 400
