"""SNS(AWS Budgets通知)トリガーのLambda。

実際コストがしきい値100%(`ACTUAL`/`PERCENTAGE`)に到達した通知を受け取った場合のみ、
`decision` Lambdaを起動しているEventBridgeルールを無効化し、エージェントの新規実行を
自動的に停止する(FR-005/006、research.md §5)。80%到達の警告通知では何もしない
(AWS Budgetsからの通知に運用者向けのメール送信を別途設定済みのため)。
"""

from __future__ import annotations

import json
import os

import boto3

from ticket_agent import audit_log

_events = boto3.client("events")

_STOP_THRESHOLD_PERCENT = 100


def lambda_handler(event, context):
    for record in event.get("Records", []):
        message = json.loads(record["Sns"]["Message"])
        if not _is_stop_threshold(message):
            continue

        rule_name = os.environ["DECISION_SCHEDULE_RULE_NAME"]
        _events.disable_rule(Name=rule_name)
        audit_log.log_operation(
            actor="budget_stop",
            ticket_id=None,
            action="BUDGET_STOP",
            result="success",
            detail=f"rule={rule_name}",
        )


def _is_stop_threshold(message: dict) -> bool:
    if message.get("notificationType") != "ACTUAL":
        return False
    try:
        threshold = float(message.get("threshold", 0))
    except (TypeError, ValueError):
        return False
    return threshold >= _STOP_THRESHOLD_PERCENT
