import os

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "test-core-tickets"

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ["TABLE_NAME"] = TABLE_NAME


@pytest.fixture(autouse=True)
def dynamodb_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        client.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "StatusIndex",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        yield
