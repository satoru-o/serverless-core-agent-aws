import boto3
import pytest
from ticket_api import repository
from ticket_api.errors import InvalidTransitionError, NotFoundError

_TEST_TABLE_NAME = "test-core-tickets"


def _raw_table():
    return boto3.resource("dynamodb", region_name="ap-northeast-1").Table(_TEST_TABLE_NAME)


def _raw_status(ticket_id: str) -> str:
    item = _raw_table().get_item(Key={"PK": f"TICKET#{ticket_id}", "SK": "METADATA"})["Item"]
    return item["status"]


def test_valid_transitions_update_status_and_record_history():
    ticket = repository.create_ticket(title="A", description="", assignee="x")

    in_progress = repository.update_status(ticket.ticket_id, "IN_PROGRESS")
    assert in_progress.status == "IN_PROGRESS"

    reopened = repository.update_status(ticket.ticket_id, "OPEN")
    assert reopened.status == "OPEN"

    history = repository.get_history(ticket.ticket_id)
    assert [h.to_status for h in history] == ["OPEN", "IN_PROGRESS", "OPEN"]
    assert [h.from_status for h in history] == [None, "OPEN", "IN_PROGRESS"]


def test_undefined_transition_is_rejected_and_state_unchanged():
    ticket = repository.create_ticket(title="A", description="", assignee="x")

    with pytest.raises(InvalidTransitionError):
        repository.update_status(ticket.ticket_id, "DONE")  # OPEN -> DONE は未定義

    assert _raw_status(ticket.ticket_id) == "OPEN"
    assert len(repository.get_history(ticket.ticket_id)) == 1


def test_update_status_raises_not_found_for_unknown_ticket():
    with pytest.raises(NotFoundError):
        repository.update_status("00000000-0000-0000-0000-000000000000", "IN_PROGRESS")


def test_concurrent_conflict_is_rejected_via_condition_expression(monkeypatch):
    """TOCTOU回帰防止テスト。

    GetItem時点では IN_PROGRESS だと信じていても、実際の書き込み時点で別要求が
    既に DONE まで進めていた場合、ConditionExpression不一致でInvalidTransitionErrorと
    なり、実際の状態(DONE)は変更されず、履歴にも誤ったfrom_statusの記録が残らないこと
    を確認する。
    """
    ticket = repository.create_ticket(title="A", description="", assignee="x")
    repository.update_status(ticket.ticket_id, "IN_PROGRESS")
    repository.update_status(ticket.ticket_id, "DONE")  # 実際の状態は DONE まで進んでいる

    stale_item = dict(_raw_table().get_item(
        Key={"PK": f"TICKET#{ticket.ticket_id}", "SK": "METADATA"}
    )["Item"])
    stale_item["status"] = "IN_PROGRESS"  # GetItem時点ではIN_PROGRESSだったと偽装する

    monkeypatch.setattr(repository, "_fetch_metadata_item", lambda _ticket_id: stale_item)

    with pytest.raises(InvalidTransitionError):
        repository.update_status(ticket.ticket_id, "OPEN")

    # 実際の状態(DONE)は変更されていない
    assert _raw_status(ticket.ticket_id) == "DONE"
    # 誤った履歴(IN_PROGRESS->OPEN)が追加されていない
    history = repository.get_history(ticket.ticket_id)
    assert [h.to_status for h in history] == ["OPEN", "IN_PROGRESS", "DONE"]
