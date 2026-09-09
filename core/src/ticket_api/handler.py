"""Lambdaエントリポイント。

API Gateway(REST API, Lambdaプロキシ統合)からのイベントを受け、
`event["resource"]` + `event["httpMethod"]` の組でルーティングする。
各ルートの実処理は、対応するユーザーストーリーの実装で `ROUTES` に登録する。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ticket_api import repository
from ticket_api.errors import DomainError, ValidationError
from ticket_api.models import VALID_STATUSES, validate_ticket_input

ROUTES: dict[tuple[str, str], Callable[[dict], dict]] = {}


def route(resource: str, method: str) -> Callable[[Callable[[dict], dict]], Callable[[dict], dict]]:
    """ROUTESにハンドラ関数を登録するデコレータ。"""

    def _register(func: Callable[[dict], dict]) -> Callable[[dict], dict]:
        ROUTES[(resource, method)] = func
        return func

    return _register


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _error_response(exc: DomainError) -> dict:
    return _response(exc.status_code, {"error": {"code": exc.code, "message": exc.message}})


def lambda_handler(event: dict, _context: Any) -> dict:
    resource = event.get("resource", "")
    method = event.get("httpMethod", "")
    handler_func = ROUTES.get((resource, method))

    if handler_func is None:
        return _response(
            501,
            {"error": {"code": "NOT_IMPLEMENTED", "message": f"{method} {resource} は未実装です"}},
        )

    try:
        return handler_func(event)
    except DomainError as exc:
        return _error_response(exc)


@route("/tickets", "POST")
def create_ticket_handler(event: dict) -> dict:
    body = json.loads(event.get("body") or "{}")
    title = body.get("title")
    description = body.get("description", "")
    assignee = body.get("assignee")

    validate_ticket_input(title=title, description=description, assignee=assignee)
    ticket = repository.create_ticket(title=title, description=description, assignee=assignee)
    return _response(201, ticket.to_response())


@route("/tickets/{ticket_id}/status", "PATCH")
def update_status_handler(event: dict) -> dict:
    ticket_id = event["pathParameters"]["ticket_id"]
    body = json.loads(event.get("body") or "{}")
    to_status = body.get("status")

    if to_status not in VALID_STATUSES:
        raise ValidationError(f"status は {VALID_STATUSES} のいずれかを指定してください")

    ticket = repository.update_status(ticket_id, to_status)
    return _response(200, ticket.to_response())


@route("/tickets", "GET")
def list_tickets_handler(event: dict) -> dict:
    query_params = event.get("queryStringParameters") or {}
    status = query_params.get("status")

    if status is not None and status not in VALID_STATUSES:
        raise ValidationError(f"status は {VALID_STATUSES} のいずれかを指定してください")

    tickets = repository.list_tickets(status=status)
    return _response(200, {"tickets": [t.to_response() for t in tickets]})


@route("/tickets/{ticket_id}", "GET")
def get_ticket_handler(event: dict) -> dict:
    ticket_id = event["pathParameters"]["ticket_id"]
    ticket = repository.get_ticket(ticket_id)
    return _response(200, ticket.to_response())


@route("/tickets/{ticket_id}/history", "GET")
def get_history_handler(event: dict) -> dict:
    ticket_id = event["pathParameters"]["ticket_id"]
    history = repository.get_history(ticket_id)
    return _response(
        200,
        {"ticket_id": ticket_id, "history": [h.to_response() for h in history]},
    )
