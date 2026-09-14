"""Amazon Bedrock(Converse API)による対応方針の判断ロジック。

`ap-northeast-1`ではAmazon Nova Microをクロスリージョン推論プロファイル経由でしか
呼び出せないため、`BEDROCK_MODEL_ID`にはモデルID自体ではなく推論プロファイルID
(例: `apac.amazon.nova-micro-v1:0`)を設定する(research.md §2)。

`COMPLETE`(チケット完了が必要という判断)は、重大操作(FR-011)であるため
`decide()`自身はチケットの状態を変更しない。`COMPLETE`を返した場合、呼び出し元
(`decision_handler.py`)は`ticket_client.update_status`を直接呼ばず、承認ステートマシンを
起動する(US3、T054)。
"""

from __future__ import annotations

import json
import os
from typing import Literal

import boto3

Decision = Literal["NO_OP", "START_PROGRESS", "COMPLETE"]

_SYSTEM_PROMPT = (
    "あなたはチケット管理システムを運用するエージェントです。与えられたチケットの状態と"
    "内容から、次に取るべき対応を1語のみで判断してください。余計な説明は不要です。"
)


def decide(ticket: dict) -> Decision:
    """1件のチケットについて対応方針を判断する。"""
    client = boto3.client("bedrock-runtime")
    response = client.converse(
        modelId=os.environ["BEDROCK_MODEL_ID"],
        system=[{"text": _SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": _build_prompt(ticket)}]}],
        inferenceConfig={"maxTokens": 16, "temperature": 0},
    )
    raw = response["output"]["message"]["content"][0]["text"]
    return _parse_decision(raw)


def _build_prompt(ticket: dict) -> str:
    return (
        f"チケット: {json.dumps(ticket, ensure_ascii=False)}\n"
        "次のいずれか1語のみで回答してください: NO_OP, START_PROGRESS, COMPLETE\n"
        "- 状態が OPEN で対応を開始すべきなら START_PROGRESS\n"
        "- 状態が IN_PROGRESS で対応が完了したとみなせるなら COMPLETE\n"
        "  (ただし実際に完了させるかどうかは人間の承認を経て決まる。ここでは提案のみ)\n"
        "- それ以外(追加対応が不要、など)は NO_OP"
    )


def _parse_decision(raw: str) -> Decision:
    normalized = raw.strip().upper()
    if "COMPLETE" in normalized:
        return "COMPLETE"
    if "START_PROGRESS" in normalized:
        return "START_PROGRESS"
    return "NO_OP"
