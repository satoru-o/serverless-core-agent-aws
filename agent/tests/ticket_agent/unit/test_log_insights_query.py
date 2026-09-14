"""CloudWatch Logs Insightsクエリ定義(agent/cloudwatch.tf)の静的検証。

Terraformを実際にapplyせずとも、クエリ文字列がFR-010(任意期間参照の手段)に必要な
フィールドを含んでいることを検証する。
"""

import re
from pathlib import Path

_CLOUDWATCH_TF = Path(__file__).resolve().parents[3] / "cloudwatch.tf"

_REQUIRED_FIELDS = ["timestamp", "actor", "ticket_id", "action", "result"]


def _query_string() -> str:
    text = _CLOUDWATCH_TF.read_text(encoding="utf-8")
    match = re.search(r'query_string\s*=\s*<<-?EOT\n(.*?)\n\s*EOT', text, re.S)
    if match is None:
        match = re.search(r'query_string\s*=\s*"([^"]*)"', text)
    assert match is not None, "query_string not found in agent/cloudwatch.tf"
    return match.group(1)


def test_query_includes_required_operation_log_fields():
    query = _query_string()

    for field in _REQUIRED_FIELDS:
        assert field in query, f"missing field {field!r} in Insights query"


def test_query_sorts_by_timestamp():
    query = _query_string()

    assert "sort" in query
    assert "timestamp" in query.split("sort", 1)[1]
