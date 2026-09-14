"""apply_decision / apply_rejection / approval_callback ロールのIAM境界テスト。

`decision`ロールと同様、Terraformを実際にapplyせずとも`agent/iam.tf`のHCLソースを
検査することで責務分離(research.md §3)を静的に検証する。
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


def _block(label: str) -> str:
    block = _extract_policy_document_block(_IAM_TF.read_text(encoding="utf-8"), label)
    return _strip_comments(block)


def test_apply_decision_has_no_states_permissions():
    block = _block("apply_decision")

    assert "execute-api:Invoke" in block
    assert "/v1/PATCH/tickets/*/status" in block
    assert "states:" not in block


def test_apply_rejection_has_no_states_permissions():
    block = _block("apply_rejection")

    assert "execute-api:Invoke" in block
    assert "/v1/PATCH/tickets/*/status" in block
    assert "states:" not in block


def test_approval_callback_has_no_ticket_api_access():
    block = _block("approval_callback")

    assert "states:SendTaskSuccess" in block
    assert "states:SendTaskFailure" in block
    assert "dynamodb:GetItem" in block
    assert "dynamodb:PutItem" in block
    assert "dynamodb:UpdateItem" in block
    assert "execute-api:Invoke" not in block
