"""Step Functionsから呼ばれ、承認された重大操作(チケット完了)を実行するLambda。

このLambdaは承認ステートマシンの`ApplyDecision`ステートからのみ呼ばれる(research.md §3)。
`decision`ロールはこの操作を発行する権限を持たない(FR-011は責務分離で担保する)。
"""

from __future__ import annotations

import os

from ticket_agent import audit_log
from ticket_agent.ticket_client import TicketClient


def lambda_handler(event, context):
    ticket_id = event["ticket_id"]
    client = TicketClient(base_url=os.environ["TICKET_API_BASE_URL"])

    audit_log.log_operation(
        actor="apply_decision", ticket_id=ticket_id, action="APPROVE", result="success"
    )
    client.update_status(ticket_id, "DONE")
    audit_log.log_operation(
        actor="apply_decision",
        ticket_id=ticket_id,
        action="TRANSITION_DONE",
        result="success",
    )
    return {"ticket_id": ticket_id, "status": "DONE"}
