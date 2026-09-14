"""API Gatewayトリガー: 承認/却下リンクの2段階確認処理(research.md §11、FR-016)。

Step 1(`GET /approvals`): 通知メール本文に直接書かれたリンク。メールクライアントや
セキュリティ製品によるプリフェッチの対象になりうるため、消費状態を記録するだけで
`states:SendTaskSuccess`/`SendTaskFailure`は一切呼ばない。

Step 2(`GET /approvals/confirm`): Step 1が返す確認ページの中にのみ現れるリンク。
人間が明示的にクリックした場合にのみ到達し、ここで初めて実際にStep Functionsへ
応答する(contracts/approval-flow.md)。
"""

from __future__ import annotations

import boto3

from ticket_agent import approval_links, audit_log

_sfn = boto3.client("stepfunctions")

_VALID_DECISIONS = ("approve", "reject")


def lambda_handler(event, context):
    query = event.get("queryStringParameters") or {}
    task_token = query.get("token")
    decision = query.get("decision")

    if not task_token or decision not in _VALID_DECISIONS:
        return _response(400, "リクエストが不正です。")

    path = event.get("path", "")
    if path.endswith("/confirm"):
        return _handle_confirm(task_token, decision)
    return _handle_request(task_token, decision)


def _handle_request(task_token: str, decision: str) -> dict:
    """Step 1: 消費状態を記録するのみ。チケット・Step Functionsへは一切書き込まない。"""
    record = approval_links.get(task_token)
    if record is not None and record.get("confirmed_at"):
        return _response(200, "このリンクは既に処理済みです。")

    approval_links.mark_consumed(task_token, decision)
    audit_log.log_operation(
        actor="approval_callback",
        ticket_id=None,
        action="REQUEST_APPROVAL_LINK_OPENED",
        result="success",
        detail=f"decision={decision}",
    )

    label = "承認" if decision == "approve" else "却下"
    confirm_url = f"/approvals/confirm?token={task_token}&decision={decision}"
    body = (
        f"<p>本当にこのチケットを{label}しますか?</p>"
        f'<p><a href="{confirm_url}">はい、{label}します</a></p>'
    )
    return _response(200, body)


def _handle_confirm(task_token: str, decision: str) -> dict:
    """Step 2: ここで初めてSendTaskSuccess/SendTaskFailureを呼ぶ。"""
    if not approval_links.mark_confirmed(task_token):
        return _response(400, "このリンクは無効か、既に処理済みです。")

    if decision == "approve":
        _sfn.send_task_success(taskToken=task_token, output='{"decision": "approve"}')
        audit_log.log_operation(
            actor="approval_callback", ticket_id=None, action="APPROVE", result="success"
        )
    else:
        _sfn.send_task_failure(
            taskToken=task_token, error="Rejected", cause="人間により却下されました"
        )
        audit_log.log_operation(
            actor="approval_callback", ticket_id=None, action="REJECT", result="success"
        )

    return _response(200, "受け付けました。処理を実行します。")


def _response(status_code: int, body: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": body,
    }
