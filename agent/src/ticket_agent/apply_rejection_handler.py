"""Step Functionsから呼ばれ、却下された重大操作の対象チケットを差し戻すLambda。

承認ステートマシンの`ApplyRejection`ステート(却下時のCatch分岐)からのみ呼ばれる。
"""

from __future__ import annotations

import os

from ticket_agent import audit_log
from ticket_agent.ticket_client import TicketClient


def lambda_handler(event, context):
    ticket_id = event["ticket_id"]
    client = TicketClient(base_url=os.environ["TICKET_API_BASE_URL"])

    audit_log.log_operation(
        actor="apply_rejection", ticket_id=ticket_id, action="REJECT", result="success"
    )
    client.update_status(ticket_id, "OPEN")
    audit_log.log_operation(
        actor="apply_rejection",
        ticket_id=ticket_id,
        action="TRANSITION_OPEN",
        result="success",
    )
    return {"ticket_id": ticket_id, "status": "OPEN"}
