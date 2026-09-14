"""承認/却下リンクの消費状態(`agent-approval-links`テーブル)への条件付きアクセス。

プリフェッチ対策の2段階確認方式(research.md §11、data-model.md「承認リンク消費状態」)
における状態遷移を担う。

- `mark_consumed`: 通知リンクへの初回アクセス時に呼ばれる。副作用はこの記録のみで、
  Ticket API・Step Functionsへの呼び出しは一切発生しない(FR-016)。
- `mark_confirmed`: 確認ページ上の明示的な操作でのみ呼ばれる。ここが成功した場合のみ
  `states:SendTaskSuccess`/`SendTaskFailure`を呼んでよい。
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError

# ステートマシンの承認タイムアウトより長く保持し、タイムアウト後の後片付けに余裕を持たせる
_TTL_MARGIN_SECONDS = 3600


def _table():
    return boto3.resource("dynamodb").Table(os.environ["APPROVAL_LINKS_TABLE_NAME"])


def mark_consumed(task_token: str, decision: str) -> bool:
    """通知リンクへの初回アクセスを記録する。

    既に記録済み(プリフェッチの繰り返し等による再アクセス)の場合は何もせず
    Falseを返す。
    """
    approval_timeout = int(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "86400"))
    ttl = int(time.time()) + approval_timeout + _TTL_MARGIN_SECONDS

    try:
        _table().put_item(
            Item={
                "task_token": task_token,
                "decision": decision,
                "consumed_at": datetime.now(UTC).isoformat(),
                "ttl": ttl,
            },
            ConditionExpression="attribute_not_exists(task_token)",
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def mark_confirmed(task_token: str) -> bool:
    """確認ページ上の明示的な操作を受けて確認済みとして記録する。

    トークンが未消費(Step 1を経ていない)、または既に確認済み(2回目以降のアクセス)の
    場合はFalseを返す。呼び出し元はFalseの場合、Step Functionsへの応答を送らない
    (二重実行防止)。
    """
    try:
        _table().update_item(
            Key={"task_token": task_token},
            UpdateExpression="SET confirmed_at = :now",
            ConditionExpression="attribute_exists(task_token) AND attribute_not_exists(confirmed_at)",
            ExpressionAttributeValues={":now": datetime.now(UTC).isoformat()},
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def get(task_token: str) -> dict | None:
    response = _table().get_item(Key={"task_token": task_token})
    return response.get("Item")
