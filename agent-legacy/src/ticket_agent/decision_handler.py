"""EventBridgeトリガーのLambdaエントリポイント(decision)。

対象チケットを取得し、`decision.py`の判断に従って許可された範囲(`IN_PROGRESS`への
遷移)のみを実行する。1回の実行あたりのTicket API呼び出し回数上限(`EXECUTION_LIMIT`)を
超えないよう監視し、上限到達時はそれ以上の呼び出しを行わず正常終了する(FR-003、
research.md §4)。

許可範囲外の呼び出し(`UnauthorizedTicketApiCallError`、API Gatewayが403を返した場合)は
処理を中断せず、拒否された事実を記録したうえで次のチケットの処理を継続する(FR-009)。

`decision.py`が`COMPLETE`(チケット完了が必要)と判断した場合、このLambda自身は
`ticket_client.update_status`を一切呼ばず、承認ステートマシンを起動するだけに留める
(FR-011/012)。実際の完了処理は、人間の承認を経て`apply_decision_handler.py`だけが行う。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import boto3

from ticket_agent import audit_log
from ticket_agent.decision import decide
from ticket_agent.errors import UnauthorizedTicketApiCallError
from ticket_agent.ticket_client import TicketClient

_TARGET_STATUSES = ("OPEN", "IN_PROGRESS")

_sfn = boto3.client("stepfunctions")


def lambda_handler(event, context):
    client = TicketClient(base_url=os.environ["TICKET_API_BASE_URL"])
    execution_limit = int(os.environ.get("EXECUTION_LIMIT", "20"))
    call_count = 0

    def _limit_reached() -> bool:
        nonlocal call_count
        if call_count >= execution_limit:
            audit_log.log_operation(
                actor="decision",
                ticket_id=None,
                action="EXECUTION_LIMIT_REACHED",
                result="rejected",
                detail=f"execution_limit={execution_limit}",
            )
            return True
        call_count += 1
        return False

    tickets: list[dict] = []
    for status in _TARGET_STATUSES:
        if _limit_reached():
            return {"processed": 0, "outcome": "limit_reached"}
        tickets.extend(client.list_tickets(status=status))

    processed = 0
    for ticket in tickets:
        ticket_id = ticket["ticket_id"]
        decision = decide(ticket)

        if decision == "START_PROGRESS":
            if _limit_reached():
                return {"processed": processed, "outcome": "limit_reached"}
            try:
                client.update_status(ticket_id, "IN_PROGRESS")
            except UnauthorizedTicketApiCallError:
                audit_log.log_operation(
                    actor="decision",
                    ticket_id=ticket_id,
                    action="UNAUTHORIZED_ATTEMPT",
                    result="rejected",
                )
            else:
                audit_log.log_operation(
                    actor="decision",
                    ticket_id=ticket_id,
                    action="TRANSITION_IN_PROGRESS",
                    result="success",
                )
        elif decision == "COMPLETE":
            _sfn.start_execution(
                stateMachineArn=os.environ["APPROVAL_STATE_MACHINE_ARN"],
                input=json.dumps(
                    {
                        "ticket_id": ticket_id,
                        "requested_action": "TRANSITION_DONE",
                        "requested_at": datetime.now(UTC).isoformat(),
                    }
                ),
            )
            audit_log.log_operation(
                actor="decision",
                ticket_id=ticket_id,
                action="REQUEST_APPROVAL",
                result="success",
            )
        processed += 1

    return {"processed": processed, "outcome": "completed"}
