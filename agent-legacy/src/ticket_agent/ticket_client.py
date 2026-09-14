"""SigV4署名付きのTicket API(Phase 1)クライアント。

Ticket APIのAPI GatewayはAWS_IAM認可(002-agent-safe-operation T004)のため、
すべてのリクエストにSigV4署名が必要となる。`boto3`/`botocore`に標準同梱の
`SigV4Auth` + `AWSRequest` で署名し、標準ライブラリの`urllib.request`で送信する
(research.md §7。`requests`等の追加ライブラリは導入しない)。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from ticket_agent.errors import TicketApiError, UnauthorizedTicketApiCallError

_SERVICE = "execute-api"


class TicketClient:
    """decision / apply_decision / apply_rejection の各Lambdaが共有するTicket APIクライアント。

    許可されるメソッドはIAMロール側(agent/iam.tf)で制限される。このクラス自体は
    与えられたURL・メソッドをそのまま署名して送信するのみで、呼び出し側(各handler)が
    どのメソッドを呼ぶかを制御する(research.md §3)。
    """

    def __init__(self, base_url: str, region: str = "ap-northeast-1"):
        self._base_url = base_url.rstrip("/")
        self._region = region

    def get_ticket(self, ticket_id: str) -> dict:
        return self._request("GET", f"/tickets/{ticket_id}")

    def list_tickets(self, status: str | None = None) -> list[dict]:
        path = "/tickets"
        if status is not None:
            path = f"{path}?{urlencode({'status': status})}"
        body = self._request("GET", path)
        return body["tickets"]

    def update_status(self, ticket_id: str, status: str) -> dict:
        return self._request(
            "PATCH",
            f"/tickets/{ticket_id}/status",
            body={"status": status},
        )

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None

        aws_request = AWSRequest(method=method, url=url, data=data)
        if data is not None:
            aws_request.headers["Content-Type"] = "application/json"

        credentials = boto3.Session().get_credentials()
        SigV4Auth(credentials, _SERVICE, self._region).add_auth(aws_request)

        signed_headers = dict(aws_request.headers.items())
        http_request = urllib.request.Request(
            url, data=data, headers=signed_headers, method=method
        )

        try:
            with urllib.request.urlopen(http_request) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise UnauthorizedTicketApiCallError(method, path) from exc
            raise TicketApiError(
                f"ticket api returned {exc.code} for {method} {path}: {exc.read()!r}"
            ) from exc
