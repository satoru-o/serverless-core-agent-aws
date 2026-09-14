import json
from unittest.mock import patch

from ticket_agent.budget_stop_handler import lambda_handler


def _sns_event(threshold: float, notification_type: str = "ACTUAL") -> dict:
    message = {
        "notificationType": notification_type,
        "thresholdType": "PERCENTAGE",
        "threshold": threshold,
        "budgetName": "agent-monthly-cost",
    }
    return {"Records": [{"Sns": {"Message": json.dumps(message)}}]}


@patch.dict("os.environ", {"DECISION_SCHEDULE_RULE_NAME": "agent-decision-schedule"})
@patch("ticket_agent.budget_stop_handler._events")
def test_disables_rule_on_100_percent_actual_threshold(mock_events, capsys):
    lambda_handler(_sns_event(100.0), None)

    mock_events.disable_rule.assert_called_once_with(Name="agent-decision-schedule")
    assert "BUDGET_STOP" in capsys.readouterr().out


@patch("ticket_agent.budget_stop_handler._events")
def test_does_nothing_on_80_percent_threshold(mock_events, capsys):
    lambda_handler(_sns_event(80.0), None)

    mock_events.disable_rule.assert_not_called()
    assert capsys.readouterr().out == ""


@patch("ticket_agent.budget_stop_handler._events")
def test_ignores_forecasted_notifications(mock_events):
    lambda_handler(_sns_event(100.0, notification_type="FORECASTED"), None)

    mock_events.disable_rule.assert_not_called()
