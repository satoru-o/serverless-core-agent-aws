"""チケットの状態遷移ルール(data-model.mdのステートマシン、FR-011/012)。"""

from __future__ import annotations

ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("OPEN", "IN_PROGRESS"),
        ("IN_PROGRESS", "DONE"),
        ("IN_PROGRESS", "OPEN"),
    }
)


def is_valid_transition(from_status: str, to_status: str) -> bool:
    return (from_status, to_status) in ALLOWED_TRANSITIONS
