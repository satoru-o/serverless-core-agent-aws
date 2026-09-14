"""操作記録(監査ログ)の構造化出力。

data-model.md「操作記録 (Operation Log)」のフィールドを持つ1行1JSONをCloudWatch Logsへ
出力する(標準出力への書き込みはLambda実行環境が自動的にCloudWatch Logsへ収集する)。
CloudWatch Logs Insightsで`timestamp`範囲を指定して期間検索できる(FR-010)。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal

Actor = Literal["decision", "apply_decision", "apply_rejection", "approval_callback", "budget_stop"]
Result = Literal["success", "rejected", "error"]


def log_operation(
    actor: Actor,
    ticket_id: str | None,
    action: str,
    result: Result,
    detail: str | None = None,
) -> None:
    """1件の操作(実際に行われた、または拒否された操作)を構造化JSONとして記録する。"""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "actor": actor,
        "ticket_id": ticket_id,
        "action": action,
        "result": result,
        "detail": detail,
    }
    print(json.dumps(record, ensure_ascii=False))
