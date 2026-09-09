"""DynamoDBアクセス層。

シングルテーブル設計(data-model.md参照)に対する読み書きをこのモジュールに集約する。
"""

from __future__ import annotations

import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Attr, Key
from boto3.dynamodb.types import TypeSerializer

from ticket_api.errors import InvalidTransitionError, NotFoundError
from ticket_api.models import (
    HistoryEntry,
    Ticket,
    metadata_sk,
    status_gsi_pk,
    ticket_pk,
)
from ticket_api.state_machine import is_valid_transition

STATUS_INDEX_NAME = "StatusIndex"

_serializer = TypeSerializer()


@lru_cache(maxsize=1)
def _table():
    table_name = os.environ["TABLE_NAME"]
    resource = boto3.resource("dynamodb")
    return resource.Table(table_name)


@lru_cache(maxsize=1)
def _client():
    return boto3.client("dynamodb")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _to_low_level(item: dict) -> dict:
    return {key: _serializer.serialize(value) for key, value in item.items()}


def create_ticket(*, title: str, description: str, assignee: str) -> Ticket:
    """チケットを新規作成する(FR-001/002/003)。

    METADATAレコードと初回HISTORYレコード(from_status=None, to_status=OPEN)を
    TransactWriteItemsで同時に書き込む(FR-013)。
    """
    ticket_id = str(uuid.uuid4())
    now = _now_iso()

    ticket = Ticket(
        ticket_id=ticket_id,
        title=title,
        description=description or "",
        assignee=assignee,
        status="OPEN",
        created_at=now,
        updated_at=now,
    )
    history_entry = HistoryEntry(
        ticket_id=ticket_id,
        from_status=None,
        to_status="OPEN",
        changed_at=now,
        suffix=uuid.uuid4().hex[:8],
    )

    table_name = os.environ["TABLE_NAME"]
    _client().transact_write_items(
        TransactItems=[
            {"Put": {"TableName": table_name, "Item": _to_low_level(ticket.to_item())}},
            {"Put": {"TableName": table_name, "Item": _to_low_level(history_entry.to_item())}},
        ]
    )
    return ticket


def _fetch_metadata_item(ticket_id: str) -> dict:
    item = _table().get_item(Key={"PK": ticket_pk(ticket_id), "SK": metadata_sk()}).get("Item")
    if item is None:
        raise NotFoundError(f"ticket_id={ticket_id} は存在しません")
    return item


def get_ticket(ticket_id: str) -> Ticket:
    """チケット単体を取得する(FR-008/009)。"""
    return Ticket.from_item(_fetch_metadata_item(ticket_id))


def get_history(ticket_id: str) -> list[HistoryEntry]:
    """チケットの状態変更履歴を発生順(changed_at昇順)で取得する(FR-013/014/015)。"""
    get_ticket(ticket_id)  # チケット自体の存在確認(存在しない場合はNotFoundError)

    response = _table().query(
        KeyConditionExpression=(
            Key("PK").eq(ticket_pk(ticket_id)) & Key("SK").begins_with("HISTORY#")
        ),
        ScanIndexForward=True,
    )
    return [HistoryEntry.from_item(item) for item in response.get("Items", [])]


def update_status(ticket_id: str, to_status: str) -> Ticket:
    """チケットの状態を変更する(FR-010〜FR-013)。

    GetItemで現状態を取得し、アプリ側で遷移可否を判定した上で、TransactWriteItemsで
    METADATA更新+新規HISTORY追加を行う。書き込み時点のstatusがGetItem時点の値と異なる
    場合(TOCTOU、別要求との競合)はConditionExpressionが失敗し、通常の未定義遷移と同じ
    InvalidTransitionErrorとして扱う(spec.md Assumptions / data-model.md参照)。
    """
    current_item = _fetch_metadata_item(ticket_id)
    current_ticket = Ticket.from_item(current_item)

    if not is_valid_transition(current_ticket.status, to_status):
        raise InvalidTransitionError(
            f"{current_ticket.status} から {to_status} への遷移は定義されていません"
        )

    now = _now_iso()
    updated_ticket = replace(current_ticket, status=to_status, updated_at=now)
    history_entry = HistoryEntry(
        ticket_id=ticket_id,
        from_status=current_ticket.status,
        to_status=to_status,
        changed_at=now,
        suffix=uuid.uuid4().hex[:8],
    )

    table_name = os.environ["TABLE_NAME"]
    try:
        _client().transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": table_name,
                        "Key": _to_low_level({"PK": ticket_pk(ticket_id), "SK": metadata_sk()}),
                        "UpdateExpression": (
                            "SET #status = :new_status, updated_at = :updated_at, "
                            "GSI1PK = :gsi1pk"
                        ),
                        "ConditionExpression": "#status = :expected_status",
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":new_status": _serializer.serialize(to_status),
                            ":updated_at": _serializer.serialize(now),
                            ":gsi1pk": _serializer.serialize(status_gsi_pk(to_status)),
                            ":expected_status": _serializer.serialize(current_ticket.status),
                        },
                    }
                },
                {
                    "Put": {
                        "TableName": table_name,
                        "Item": _to_low_level(history_entry.to_item()),
                    }
                },
            ]
        )
    except _client().exceptions.TransactionCanceledException as exc:
        raise InvalidTransitionError(
            "状態が別の要求によって変更されたため、この遷移は成立しませんでした。"
            "最新の状態を確認して再試行してください"
        ) from exc

    return updated_ticket


def list_tickets(status: str | None = None) -> list[Ticket]:
    """チケット一覧を取得する(FR-005/006)。

    statusが指定された場合はStatusIndexへのQuery、未指定の場合はScan(METADATAのみ)。
    """
    if status is not None:
        response = _table().query(
            IndexName=STATUS_INDEX_NAME,
            KeyConditionExpression=Key("GSI1PK").eq(status_gsi_pk(status)),
        )
    else:
        response = _table().scan(FilterExpression=Attr("SK").eq(metadata_sk()))

    return [Ticket.from_item(item) for item in response.get("Items", [])]
