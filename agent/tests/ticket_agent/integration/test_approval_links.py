import boto3
import pytest
from moto import mock_aws

from ticket_agent import approval_links

_TABLE_NAME = "agent-approval-links"


@pytest.fixture
def approval_links_table(monkeypatch):
    monkeypatch.setenv("APPROVAL_LINKS_TABLE_NAME", _TABLE_NAME)
    monkeypatch.setenv("APPROVAL_TIMEOUT_SECONDS", "86400")
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        client.create_table(
            TableName=_TABLE_NAME,
            KeySchema=[{"AttributeName": "task_token", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "task_token", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


def test_mark_consumed_succeeds_only_on_first_access(approval_links_table):
    assert approval_links.mark_consumed("token-1", "approve") is True
    # プリフェッチによる再アクセス相当。2回目は既存レコードを変更しない
    assert approval_links.mark_consumed("token-1", "reject") is False

    item = approval_links.get("token-1")
    assert item["decision"] == "approve"
    assert "confirmed_at" not in item


def test_mark_confirmed_succeeds_only_once(approval_links_table):
    approval_links.mark_consumed("token-2", "approve")

    assert approval_links.mark_confirmed("token-2") is True
    # 2回目(確認リンクへの再アクセス)は失敗し、二重実行を防ぐ
    assert approval_links.mark_confirmed("token-2") is False

    item = approval_links.get("token-2")
    assert item["confirmed_at"] is not None


def test_mark_confirmed_returns_false_for_unknown_token(approval_links_table):
    assert approval_links.mark_confirmed("never-consumed-token") is False
