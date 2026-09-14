"""decisionロールのIAM境界テスト。

Terraformを実際にapplyせずとも、`agent/iam.tf`のHCLソースを検査することで
FR-001/FR-002(許可範囲の限定・範囲外操作の拒否)を静的に検証する。

`decision`ロールはUS3(T052)で`states:StartExecution`を追加で許可されるが、
`states:SendTaskSuccess`/`SendTaskFailure`(トークン応答、`approval_callback`専用)や
`dynamodb:*`、`POST /tickets`は将来にわたって一切許可してはならない
(research.md §3の責務分離)。
"""

import re
from pathlib import Path

_IAM_TF = Path(__file__).resolve().parents[3] / "iam.tf"


def _strip_comments(hcl: str) -> str:
    """HCLの`#`行コメントを取り除く(コメント内の説明文が誤検知の原因になるため)。"""
    return re.sub(r"#.*", "", hcl)


def _extract_policy_document_block(text: str, label: str) -> str:
    """`label`のHCLブロックをブレースの対応関係から抽出する。

    HCLの文字列補間(`"${...}"`)は文字列の中に`{`/`}`を含むため、単純な
    ブレースカウントでは深さがずれてしまう。ダブルクォート文字列の内部にいる間は
    ブレースを数えないようにする。
    """
    marker = f'data "aws_iam_policy_document" "{label}"'
    start = text.index(marker)
    brace_start = text.index("{", start)
    depth = 0
    in_string = False
    i = brace_start
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[brace_start : i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces for block {label!r}")


def _decision_policy_block() -> str:
    block = _extract_policy_document_block(_IAM_TF.read_text(encoding="utf-8"), "decision")
    return _strip_comments(block)


def test_decision_policy_allows_only_expected_ticket_api_methods():
    block = _decision_policy_block()

    assert "execute-api:Invoke" in block
    assert "/v1/GET/tickets" in block
    assert "/v1/GET/tickets/*" in block
    assert "/v1/PATCH/tickets/*/status" in block


def test_decision_policy_never_allows_post_tickets():
    assert "/POST/tickets" not in _decision_policy_block()


def test_decision_policy_never_allows_direct_dynamodb_access():
    assert "dynamodb:" not in _decision_policy_block()


def test_decision_policy_never_allows_sending_task_tokens():
    block = _decision_policy_block()

    assert "states:SendTaskSuccess" not in block
    assert "states:SendTaskFailure" not in block
