# Design: DynamoDB data model & MCP surface

This document explains *why* the table looks the way it does. It follows the DynamoDB rule:
**list the access patterns first, then design keys that serve each one with a single `Query` or `GetItem`.**

## 1. Access patterns

| # | Question the AI agent needs answered | Frequency | Served by |
|---|---|---|---|
| AP1 | Incidents for service X, newest first | very high | Query PK + `begins_with(SK, "INCIDENT#")`, descending |
| AP2 | Incidents for X mentioning a keyword | high | AP1 + `FilterExpression contains(...)` |
| AP3 | One incident by ID | high | `GetItem` |
| AP4 | All *open* incidents, any service | medium | `Query GSI1` on `STATUS#open` |
| AP5 | Resolve an incident, exactly once | medium | `UpdateItem` + `ConditionExpression` |
| AP6 | Attach a note to X that expires after N days | low | `PutItem` with TTL attribute |
| AP7 | Notes for service X | low | Query PK + `begins_with(SK, "NOTE#")` |
| AP8 | Incident count / last incident for X | medium | `GetItem` on the META item |

## 2. Table `incident_memory`

Single table, on-demand billing, one GSI, TTL enabled on `expires_at`.

| Entity | PK | SK | GSI1PK | GSI1SK | Data attributes |
|---|---|---|---|---|---|
| Incident | `SERVICE#<svc>` | `INCIDENT#<iso-ts>#<ulid>` | `STATUS#open` \| `STATUS#resolved` | `<iso-ts>` | incident_id, service, severity, summary, root_cause, fix, status, created_at, resolved_at |
| Note | `SERVICE#<svc>` | `NOTE#<iso-ts>` | — | — | note, author, created_at, **expires_at** |
| Meta | `SERVICE#<svc>` | `META` | — | — | service, incident_count, last_incident_at |

### Key decisions

**Partition by service.** Every question in the table above is either "about one service" or "about status". Making the service the partition key means AP1, AP2, AP7 and AP8 each hit a single partition — the cheapest possible read.

**Timestamp inside the sort key.** ISO-8601 UTC strings sort lexicographically in time order, so `ScanIndexForward=False` gives "newest first" for free and `between()` gives date ranges. A ULID suffix guarantees uniqueness when two incidents land in the same second.

**Entity prefixes (`INCIDENT#`, `NOTE#`, `META`).** Three entity types share one partition. Prefixes let a query select one type with `begins_with`, or fetch everything about a service with a bare PK query.

**GSI1 keyed on status.** "All open incidents" cuts across partitions. Without an index it would be a `Scan` (reads the whole table). GSI1 re-keys items by `STATUS#…` so it becomes a `Query`. Only incidents carry GSI1 attributes, so notes and meta items are automatically excluded from the index (a *sparse* index).

**Conditional resolve.** `ConditionExpression="#status = :open"` is evaluated atomically server-side. Two agents resolving the same incident concurrently → exactly one succeeds; the other gets `ConditionalCheckFailedException`, surfaced to the model as a clear error. No read-modify-write, no locks.

**Atomic counter in META.** `ADD incident_count :one` increments without reading first, so concurrent writers never lose updates.

**TTL on notes.** Runbook notes are transient by nature. Setting `expires_at` (epoch seconds) lets DynamoDB delete them for free, typically within 48 h of expiry.

**`incident_id` = `service|SK`.** An opaque string the model can pass back; the server splits it to rebuild the exact key for `GetItem`/`UpdateItem`.

## 3. What this design deliberately does not do

| Need | Why not now | How to add it |
|---|---|---|
| Search by severity across services | No access pattern requires it yet | Add `GSI2PK = SEV#<severity>`, `GSI2SK = <ts>` |
| Full-text search | `contains()` is a post-read filter; fine for hundreds of incidents per service, not millions | DynamoDB Streams → OpenSearch |
| Hot partition protection | A single very noisy service could exceed per-partition throughput | Write-shard: `SERVICE#<svc>#<0..N>`, fan out reads |
| Pagination | Tools return ≤ 50 items and the model rarely needs more | Return `LastEvaluatedKey` as a cursor argument |

## 4. MCP surface

| Primitive | Name | Backed by |
|---|---|---|
| tool | `record_incident` | AP-write + META counter |
| tool | `find_similar_incidents` | AP1 / AP2 |
| tool | `get_incident` | AP3 |
| tool | `update_incident_status` | AP5 |
| tool | `list_open_incidents` | AP4 |
| tool | `add_runbook_note` | AP6 |
| tool | `service_stats` | AP8 |
| resource | `incident://{service}/latest` | AP1 (limit 1) |
| prompt | `triage_alert` | orchestrates the tools above |

Tool descriptions are written for the model, not for humans: each states *when* to use the tool, because the model selects tools from descriptions alone.

## 5. Security model (production)

- The server holds **no AWS credentials**; boto3 obtains temporary ones from the EC2 instance role via IMDS.
- The role's policy allows only `GetItem, PutItem, UpdateItem, Query, DescribeTable` on this table and its GSI — no `Scan`, no `DeleteItem`, no other tables.
- nginx terminates TLS and enforces a bearer token before any request reaches the app; the app listens on localhost only.
