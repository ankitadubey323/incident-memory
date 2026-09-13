"""DynamoDB access layer — every table read/write lives here.

Single-table design (see docs/DESIGN.md):
  Incident : PK=SERVICE#<svc>  SK=INCIDENT#<ts>#<ulid>  GSI1PK=STATUS#<open|resolved>  GSI1SK=<ts>
  Note     : PK=SERVICE#<svc>  SK=NOTE#<ts>            expires_at (TTL)
  Meta     : PK=SERVICE#<svc>  SK=META                 incident_count, last_incident_at
"""
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from ulid import ULID

from . import config

_resource = boto3.resource(
    "dynamodb", region_name=config.AWS_REGION, endpoint_url=config.DDB_ENDPOINT
)
table = _resource.Table(config.TABLE_NAME)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pk(service: str) -> str:
    return f"SERVICE#{service}"


def _clean(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """DynamoDB returns numbers as Decimal; convert so results serialise to JSON."""
    if item is None:
        return None
    return {k: int(v) if isinstance(v, Decimal) else v for k, v in item.items()}


# ---------------------------------------------------------------- incidents
def record_incident(service: str, severity: str, summary: str,
                    root_cause: str = "", fix: str = "") -> dict[str, Any]:
    ts = _now()
    sk = f"INCIDENT#{ts}#{ULID()}"
    item = {
        "PK": _pk(service), "SK": sk,
        "GSI1PK": "STATUS#open", "GSI1SK": ts,
        "incident_id": f"{service}|{sk}",
        "service": service, "severity": severity, "summary": summary,
        "root_cause": root_cause, "fix": fix,
        "status": "open", "created_at": ts,
    }
    table.put_item(Item=item)
    # atomic counter on the service META item (no read-modify-write race)
    table.update_item(
        Key={"PK": _pk(service), "SK": "META"},
        UpdateExpression="ADD incident_count :one SET last_incident_at = :ts, service = :svc",
        ExpressionAttributeValues={":one": 1, ":ts": ts, ":svc": service},
    )
    return item


def find_similar(service: str, keyword: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(_pk(service)) & Key("SK").begins_with("INCIDENT#"),
        "ScanIndexForward": False,  # newest first
        "Limit": 50,
    }
    if keyword:
        kwargs["FilterExpression"] = (
            Attr("summary").contains(keyword) | Attr("root_cause").contains(keyword)
        )
    items = table.query(**kwargs)["Items"]
    return [_clean(i) for i in items[:limit]]


def get_incident(incident_id: str) -> dict[str, Any] | None:
    service, sk = incident_id.split("|", 1)
    return _clean(table.get_item(Key={"PK": _pk(service), "SK": sk}).get("Item"))


def resolve_incident(incident_id: str, root_cause: str, fix: str) -> dict[str, Any]:
    service, sk = incident_id.split("|", 1)
    try:
        resp = table.update_item(
            Key={"PK": _pk(service), "SK": sk},
            UpdateExpression=(
                "SET #s = :resolved, GSI1PK = :gsi, root_cause = :rc, fix = :fx, resolved_at = :ts"
            ),
            ConditionExpression="#s = :open",  # optimistic locking: only resolve once
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":resolved": "resolved", ":open": "open", ":gsi": "STATUS#resolved",
                ":rc": root_cause, ":fx": fix, ":ts": _now(),
            },
            ReturnValues="ALL_NEW",
        )
        return _clean(resp["Attributes"])
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ValueError(f"Incident {incident_id} is not open (already resolved or missing)")
        raise


def list_open(limit: int = 20) -> list[dict[str, Any]]:
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq("STATUS#open"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [_clean(i) for i in resp["Items"]]


# ---------------------------------------------------------------- notes / stats
def add_note(service: str, note: str, author: str = "claude", ttl_days: int = 30) -> dict[str, Any]:
    ts = _now()
    item = {
        "PK": _pk(service), "SK": f"NOTE#{ts}",
        "note": note, "author": author, "created_at": ts,
        "expires_at": int(time.time() + ttl_days * 86400),  # TTL attribute
    }
    table.put_item(Item=item)
    return item


def list_notes(service: str) -> list[dict[str, Any]]:
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(_pk(service)) & Key("SK").begins_with("NOTE#"),
        ScanIndexForward=False,
    )
    return [_clean(i) for i in resp["Items"]]


def service_stats(service: str) -> dict[str, Any]:
    item = table.get_item(Key={"PK": _pk(service), "SK": "META"}).get("Item")
    return _clean(item) or {"service": service, "incident_count": 0, "last_incident_at": None}
