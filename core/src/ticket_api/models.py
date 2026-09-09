"""チケット管理APIのドメインモデル。

data-model.md のエンティティ定義・DynamoDB物理データモデルに対応する。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ticket_api.errors import ValidationError

VALID_STATUSES = ("OPEN", "IN_PROGRESS", "DONE")


def validate_ticket_input(title: str | None, description: str | None, assignee: str | None) -> None:
    """チケット作成時の必須項目バリデーション(FR-004)。

    title・assigneeは空文字・未指定を許容しない。descriptionは任意項目。
    """
    if title is None or not title.strip():
        raise ValidationError("title は必須です(空文字は不可)")
    if assignee is None or not assignee.strip():
        raise ValidationError("assignee は必須です(空文字は不可)")


def ticket_pk(ticket_id: str) -> str:
    return f"TICKET#{ticket_id}"


def metadata_sk() -> str:
    return "METADATA"


def history_sk(changed_at: str, suffix: str) -> str:
    return f"HISTORY#{changed_at}#{suffix}"


def status_gsi_pk(status: str) -> str:
    return f"STATUS#{status}"


def status_gsi_sk(created_at: str, ticket_id: str) -> str:
    return f"{created_at}#{ticket_id}"


@dataclass
class Ticket:
    ticket_id: str
    title: str
    description: str
    assignee: str
    status: str
    created_at: str
    updated_at: str

    def to_item(self) -> dict:
        return {
            "PK": ticket_pk(self.ticket_id),
            "SK": metadata_sk(),
            "ticket_id": self.ticket_id,
            "title": self.title,
            "description": self.description,
            "assignee": self.assignee,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "GSI1PK": status_gsi_pk(self.status),
            "GSI1SK": status_gsi_sk(self.created_at, self.ticket_id),
        }

    @staticmethod
    def from_item(item: dict) -> Ticket:
        return Ticket(
            ticket_id=item["ticket_id"],
            title=item["title"],
            description=item["description"],
            assignee=item["assignee"],
            status=item["status"],
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )

    def to_response(self) -> dict:
        return asdict(self)


@dataclass
class HistoryEntry:
    ticket_id: str
    from_status: str | None
    to_status: str
    changed_at: str
    suffix: str

    def to_item(self) -> dict:
        return {
            "PK": ticket_pk(self.ticket_id),
            "SK": history_sk(self.changed_at, self.suffix),
            "ticket_id": self.ticket_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "changed_at": self.changed_at,
        }

    @staticmethod
    def from_item(item: dict) -> HistoryEntry:
        sk = item["SK"]
        suffix = sk.split("#", 2)[2] if sk.count("#") >= 2 else ""
        return HistoryEntry(
            ticket_id=item["ticket_id"],
            from_status=item.get("from_status"),
            to_status=item["to_status"],
            changed_at=item["changed_at"],
            suffix=suffix,
        )

    def to_response(self) -> dict:
        return {
            "from_status": self.from_status,
            "to_status": self.to_status,
            "changed_at": self.changed_at,
        }
