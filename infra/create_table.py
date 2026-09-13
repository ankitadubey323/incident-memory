"""Create the `incident_memory` table (PK/SK + GSI1 + TTL).

Works against DynamoDB Local when DDB_ENDPOINT is set, and against real AWS
when it is unset. Safe to re-run: exits cleanly if the table already exists.
"""
import os

import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "eu-central-1")
ENDPOINT = os.getenv("DDB_ENDPOINT")  # e.g. http://localhost:8000 ; None -> real AWS
TABLE = os.getenv("TABLE_NAME", "incident_memory")


def main() -> None:
    ddb = boto3.client("dynamodb", region_name=REGION, endpoint_url=ENDPOINT)
    target = ENDPOINT or f"AWS ({REGION})"

    try:
        ddb.create_table(
            TableName=TABLE,
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
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"table '{TABLE}' already exists on {target}")
            return
        raise

    ddb.get_waiter("table_exists").wait(TableName=TABLE)
    ddb.update_time_to_live(
        TableName=TABLE,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "expires_at"},
    )
    print(f"created table '{TABLE}' with GSI1 and TTL on {target}")


if __name__ == "__main__":
    main()
