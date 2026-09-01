# Onboarding

This guide brings a new contributor from "I have a laptop and AWS access" to "I can ship a fix" in about an hour.

## Prerequisites

- AWS account access for `<account-id>` with permissions to read CDK outputs, push to ECR, and update ECS services. SSO via IAM Identity Center is recommended.
- AWS CLI v2 (`aws --version` ≥ 2.20)
- Node.js 20.x (`node -v`)
- Python 3.12 (`python3 --version`)
- Docker with `linux/arm64` build support (`docker buildx ls` should list a `linux/arm64` builder)
- AWS CDK v2.150 (`npx cdk --version`)
- jq, curl, openssl

## Initial Setup

```bash
# Clone
git clone https://github.com/dediwsn/retail-ontology.git
cd ontology-retail

# Backend (runtime + dev deps for offline tests)
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
pip install -r requirements-dev.txt   # pytest, pytest-asyncio, httpx — for `pytest tests`

# Frontend
(cd web && npm ci)

# Infra (also installs jest + ts-jest for snapshot tests)
(cd infra-cdk && npm ci)

# Configure local env
cp .env.example .env
# Fill values from CDK outputs:
aws cloudformation describe-stacks --region ap-northeast-2 \
  --stack-name OntologyRetailData --query 'Stacks[0].Outputs' --output json
aws cloudformation describe-stacks --region ap-northeast-2 \
  --stack-name OntologyRetailCompute --query 'Stacks[0].Outputs' --output json
```

## Verify Access

```bash
# AWS identity
aws sts get-caller-identity

# Bedrock model access
aws bedrock list-foundation-models --region ap-northeast-2 \
  --query 'modelSummaries[?contains(modelId, `claude-sonnet-4-6`)]'

# Neptune (must run from inside the VPC; will fail from a laptop — that's expected)
nslookup ontology-retail-dev-neptune.cluster-<cluster-suffix>.ap-northeast-2.neptune.amazonaws.com
```

## Run Tests

Before pushing, run the same gates CI runs (~15s total):

```bash
# 1. Python AST validation
python3 -m compileall -q api data scripts

# 2. TypeScript type-check
(cd web && npx tsc --noEmit)
(cd infra-cdk && npx tsc --noEmit)

# 3. Offline pytest suite (28 tests)
pytest tests -q

# 4. CDK snapshot tests
(cd infra-cdk && npx jest --ci)
```

Local pre-commit hook installer at `scripts/install-hooks.sh` only wires the commit-msg trailer-stripper today; the other gates are CI-only. Run them manually or via `.claude/commands/test-all.md`.

## Run Locally

```bash
# Backend (requires VPN or SSM port-forward to Neptune)
source .venv/bin/activate
ONTOLOGY_ENV=dev uvicorn api.main:app --reload --port 8000

# Frontend
(cd web && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev)
```

For most demo work you don't need to run locally — the deployed CloudFront URL serves both pieces. Local dev is only required for debugging Lambda@Edge or making tight UI iteration loops.

## Build & Deploy

```bash
# 1. Build + push API image (ARM64)
TAG="$(git rev-parse --short HEAD)-$(date +%s)"
aws ecr get-login-password --region ap-northeast-2 \
  | docker login --username AWS --password-stdin <account>.dkr.ecr.ap-northeast-2.amazonaws.com
docker build --platform linux/arm64 -f api/Dockerfile \
  -t <account>.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:$TAG \
  -t <account>.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:latest .
docker push <account>.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:$TAG
docker push <account>.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:latest

# 2. Force ECS rollout (uses :latest from new push)
aws ecs update-service --region ap-northeast-2 \
  --cluster ontology-retail-dev-cluster --service ontology-retail-dev-api \
  --force-new-deployment

# 3. Repeat steps 1-2 for web image if frontend changed
```

For deterministic rollouts (avoiding `:latest` cache traps), register a new task-definition revision pinning the SHA-tagged image — see [docs/runbooks/](runbooks/) for the snippet.

## Reload Synthetic Data

```bash
# Run loader as a one-shot ECS task in the same VPC/SG as the API
cat > /tmp/loader-overrides.json <<EOF
{
  "containerOverrides": [{
    "name": "api",
    "command": ["python","-m","data.load","--neptune","--opensearch","--from-s3"],
    "environment": [
      {"name": "SYNTHETIC_DATA_BUCKET", "value": "ontology-retail-dev-synthetic-data-<account-id>"}
    ]
  }]
}
EOF
aws ecs run-task --region ap-northeast-2 \
  --cluster ontology-retail-dev-cluster \
  --task-definition ontology-retail-dev-api \
  --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={subnets=[<api-subnet-1>,<api-subnet-2>],securityGroups=[<api-sg>],assignPublicIp=DISABLED}' \
  --overrides file:///tmp/loader-overrides.json
```

## Common Pitfalls

- **Building x86 images by mistake** — Fargate ARM64 will reject the task. Always pass `--platform linux/arm64`.
- **`:latest` not pulling new image** — ECS caches the previous digest. Either register a SHA-pinned task definition or wait + force-deploy twice.
- **`open_cypher(query, params)` 500** — `parameters` is keyword-only; call as `open_cypher(query, parameters={...})`.
- **F-string SyntaxError on Korean labels** — never escape quotes inside f-string expressions; extract to a local variable first.
- **Cognito callback rejected after domain change** — `update-user-pool-client` has PUT semantics; always re-pass full config or it clobbers OAuth flows/scopes (see SECURITY.md).

## Where to Go Next

- Project memory and conventions: [CLAUDE.md](../CLAUDE.md) (and module-level `CLAUDE.md` in each subdirectory)
- Test conventions: [tests/CLAUDE.md](../tests/CLAUDE.md)
- Architecture: [docs/architecture.md](architecture.md)
- API surface: [docs/api-reference.md](api-reference.md)
- Decisions: [docs/decisions/](decisions/) — ADRs 0001 (AgentCore Memory), 0002 (CloudTrail), 0003 (Lambda@Edge), 0004 (Cognito)
- Runbooks: [docs/runbooks/](runbooks/) (only `.template.md` today; runbooks are TODO)
- Project harness: `.claude/` — agents, skills, hooks, commands; run `harness-eval:standard` to score
- Security posture: [SECURITY.md](../SECURITY.md)
