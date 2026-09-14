import json

from ticket_agent.audit_log import log_operation

_EXPECTED_FIELDS = {"timestamp", "actor", "ticket_id", "action", "result", "detail"}


def test_log_operation_emits_structured_json_with_expected_fields(capsys):
    log_operation(
        actor="decision",
        ticket_id="abc-123",
        action="TRANSITION_IN_PROGRESS",
        result="success",
        detail=None,
    )

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip())

    assert set(record.keys()) == _EXPECTED_FIELDS
    assert record["actor"] == "decision"
    assert record["ticket_id"] == "abc-123"
    assert record["action"] == "TRANSITION_IN_PROGRESS"
    assert record["result"] == "success"
    assert record["detail"] is None
    # ISO 8601形式であること(末尾までパース可能であること)を軽く確認する
    assert "T" in record["timestamp"]


def test_log_operation_allows_null_ticket_id_for_non_ticket_actions(capsys):
    log_operation(
        actor="budget_stop",
        ticket_id=None,
        action="BUDGET_STOP",
        result="success",
        detail="threshold=100%",
    )

    record = json.loads(capsys.readouterr().out.strip())

    assert record["ticket_id"] is None
    assert record["detail"] == "threshold=100%"
