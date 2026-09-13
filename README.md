# Incident Memory

An MCP server that gives AI agents long-term memory of production incidents, backed by Amazon DynamoDB.
Full guide: [docs/Incident_Memory_Project_Guide.md](docs/Incident_Memory_Project_Guide.md)

## Local development (Docker only — no AWS account needed)

```bash
# 1. Start DynamoDB Local + admin UI
docker-compose -f deploy/docker-compose.local.yml up -d

# 2. Load local settings (dummy credentials; DynamoDB Local accepts anything)
cp env.local.example .env
set -a; source .env; set +a

# 3. Install and create the table
uv sync
uv run python infra/create_table.py

# 4. Verify every DynamoDB access pattern
uv run python scripts/smoke_test.py

# 5. Explore the MCP server in a browser
npx @modelcontextprotocol/inspector uv run incident-memory
```

- DynamoDB Local: http://localhost:8002
- DynamoDB admin UI: http://localhost:8003

## Connect Claude Code (local, stdio)

```bash
claude mcp add incident-memory \
  -e DDB_ENDPOINT=http://localhost:8002 -e AWS_ACCESS_KEY_ID=local \
  -e AWS_SECRET_ACCESS_KEY=local -e AWS_REGION=eu-central-1 -e TABLE_NAME=incident_memory \
  -- uv run --directory "$PWD" incident-memory
```

## Run tests (no Docker or AWS needed)

```bash
uv run pytest -q          # 12 tests: DynamoDB layer (moto) + MCP layer (in-process client)
```

## Try the production image locally (HTTP mode, as on EC2)

```bash
docker build -t incident-memory -f deploy/Dockerfile .
docker run -d --name incident-memory-app --network deploy_default -p 127.0.0.1:8080:8080 \
  -e DDB_ENDPOINT=http://dynamodb:8000 -e AWS_ACCESS_KEY_ID=local -e AWS_SECRET_ACCESS_KEY=local \
  incident-memory
# MCP endpoint: http://127.0.0.1:8080/mcp   (Inspector: transport "Streamable HTTP")
docker rm -f incident-memory-app
```

## Project layout

```
src/incident_memory/   server.py (MCP tools/resource/prompt) · db.py (DynamoDB) · config.py
tests/                 pytest + moto + in-process MCP client
infra/                 create_table.py · iam_policy.json (least-privilege EC2 role)
deploy/                Dockerfile · docker-compose.local.yml · nginx.conf · incident-memory.service
docs/                  DESIGN.md (data model rationale) · full project guide (md + pdf)
.github/workflows/     CI: pytest + docker build on every push
```

## Deploying to AWS EC2

See sections 8–10 of the guide (IAM role, Docker, nginx, HTTPS).
