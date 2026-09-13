"""Test fixtures: an in-memory DynamoDB (moto) with the real table schema.

No Docker, no AWS, no network — `uv run pytest` works anywhere.
"""
import importlib
import os

import boto3
import pytest
from moto import mock_aws

# Must be set before boto3/db.py are imported anywhere in the test session.
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_REGION"] = "eu-central-1"
os.environ["AWS_DEFAULT_REGION"] = "eu-central-1"
os.environ["TABLE_NAME"] = "incident_memory"
os.environ.pop("DDB_ENDPOINT", None)  # talk to moto, not DynamoDB Local


@pytest.fixture
def db():
    """Fresh mocked table + reloaded db module for every test."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-central-1")
        client.create_table(
            TableName="incident_memory",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
        )
        from incident_memory import config, db as db_module
        importlib.reload(config)
        importlib.reload(db_module)  # rebinds boto3 resource inside the mock
        yield db_module
