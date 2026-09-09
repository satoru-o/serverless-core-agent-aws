import boto3
from ticket_api import repository

_TEST_TABLE_NAME = "test-core-tickets"


def _raw_table():
    return boto3.resource("dynamodb", region_name="ap-northeast-1").Table(_TEST_TABLE_NAME)


def test_create_ticket_writes_metadata_and_initial_history():
    ticket = repository.create_ticket(
        title="サンプルチケット", description="説明", assignee="satoru-o"
    )

    assert ticket.status == "OPEN"
    assert ticket.title == "サンプルチケット"
    assert ticket.assignee == "satoru-o"
    assert ticket.created_at == ticket.updated_at

    table = _raw_table()

    metadata_item = table.get_item(Key={"PK": f"TICKET#{ticket.ticket_id}", "SK": "METADATA"})[
        "Item"
    ]
    assert metadata_item["status"] == "OPEN"
    assert metadata_item["title"] == "サンプルチケット"
    assert metadata_item["GSI1PK"] == "STATUS#OPEN"

    history_items = table.query(
        KeyConditionExpression=(
            boto3.dynamodb.conditions.Key("PK").eq(f"TICKET#{ticket.ticket_id}")
            & boto3.dynamodb.conditions.Key("SK").begins_with("HISTORY#")
        )
    )["Items"]
    assert len(history_items) == 1
    assert history_items[0]["from_status"] is None
    assert history_items[0]["to_status"] == "OPEN"
    assert history_items[0]["changed_at"] == ticket.created_at


def test_create_ticket_generates_unique_ids():
    first = repository.create_ticket(title="A", description="", assignee="x")
    second = repository.create_ticket(title="B", description="", assignee="y")

    assert first.ticket_id != second.ticket_id
