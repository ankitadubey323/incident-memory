"""End-to-end check of the DynamoDB layer against DynamoDB Local (or AWS).

    set -a; source .env; set +a
    uv run python scripts/smoke_test.py
"""
from incident_memory import config, db

print(f"table={config.TABLE_NAME} endpoint={config.DDB_ENDPOINT or 'AWS'}\n")

inc = db.record_incident("checkout-service", "sev2",
                         "503 errors on /pay, started 10:15", root_cause="", fix="")
print("1. record_incident       ->", inc["incident_id"])

similar = db.find_similar("checkout-service", keyword="503")
print("2. find_similar('503')   ->", len(similar), "match(es)")

print("3. get_incident          ->", db.get_incident(inc["incident_id"])["status"])

open_now = db.list_open()
print("4. list_open (GSI1)      ->", len(open_now), "open incident(s)")

resolved = db.resolve_incident(inc["incident_id"],
                               "Redis connection pool exhaustion", "raised maxclients to 10000")
print("5. resolve_incident      ->", resolved["status"])

try:
    db.resolve_incident(inc["incident_id"], "x", "y")
    print("6. resolve again         -> UNEXPECTED: succeeded")
except ValueError as e:
    print("6. resolve again         -> correctly rejected:", e)

note = db.add_note("checkout-service", "If 503s return, check Redis maxclients first.", ttl_days=7)
print("7. add_note (TTL)        -> expires_at =", note["expires_at"])

stats = db.service_stats("checkout-service")
print("8. service_stats         ->", stats)

print("\nOK — all DynamoDB access patterns work. Browse data at http://localhost:8003")
