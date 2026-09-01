# Runbook: Production Deploy (api / web)

**When to use**: shipping a code change to the deployed environment (account `061525506239`, region `ap-northeast-2`, cluster `ontology-retail-dev-cluster`).

**Pre-conditions**:
- All code merged to `main` and pushed.
- ECR repos `ontology-retail-dev-api` and `ontology-retail-dev-web` exist (created by `infra-cdk` ComputeStack).
- Local docker daemon is on ARM64 (`docker info --format '{{.Architecture}}'` should print `aarch64`); otherwise `--platform linux/arm64` triggers QEMU and builds 5–10× slower.

---

## 1. Set deploy variables

```bash
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export AWS_REGION="ap-northeast-2"
export TAG="$(git rev-parse --short HEAD)-$(date +%s)"
```

The `${SHA}-${epoch}` tag avoids `:latest` cache traps and is unique per push.

## 2. ECR login (12-hour token)

```bash
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

If push later returns `denied: Your authorization token has expired`, re-run this command — see [`ecr-auth-refresh.md`](ecr-auth-refresh.md).

## 3. Build (parallel, ARM64)

Build api + web in parallel using two shells or background jobs. Both Dockerfiles are ARM64 only.

```bash
# API
docker build --platform linux/arm64 -f api/Dockerfile \
  -t $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-api:$TAG \
  -t $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-api:latest .

# Web
docker build --platform linux/arm64 -f web/Dockerfile \
  -t $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-web:$TAG \
  -t $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-web:latest .
```

> **Skip a service if unchanged**. If only `api/` changed, skip the web build to save 1–2 min. Use `git diff --name-only HEAD~1` to confirm.

## 4. Push (both tags)

```bash
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-api:$TAG
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-api:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-web:$TAG
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-web:latest
```

## 5. Register SHA-pinned task definition (avoids `:latest` cache)

For each service that changed (api / web), pull the active task definition, replace the container image, and register a new revision. The api section below is the pattern; the web section is identical with the names swapped.

```bash
NEW_IMAGE=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ontology-retail-dev-api:$TAG

aws ecs describe-task-definition --task-definition ontology-retail-dev-api \
  --region $AWS_REGION --query 'taskDefinition' > /tmp/td-api-current.json

python3 - <<PY
import json
td = json.load(open('/tmp/td-api-current.json'))
for k in ('taskDefinitionArn','revision','status','requiresAttributes','compatibilities',
         'registeredAt','registeredBy','deregisteredAt'):
    td.pop(k, None)
td['containerDefinitions'][0]['image'] = '$NEW_IMAGE'
json.dump(td, open('/tmp/td-api-new.json','w'))
PY

NEW_REV=$(aws ecs register-task-definition --region $AWS_REGION \
  --cli-input-json file:///tmp/td-api-new.json \
  --query 'taskDefinition.revision' --output text)

aws ecs update-service --cluster ontology-retail-dev-cluster \
  --service ontology-retail-dev-api \
  --task-definition ontology-retail-dev-api:$NEW_REV \
  --force-new-deployment --region $AWS_REGION
```

## 6. Wait for stable

```bash
aws ecs wait services-stable --cluster ontology-retail-dev-cluster \
  --services ontology-retail-dev-api ontology-retail-dev-web --region $AWS_REGION
```

Default timeout is ~10 minutes (100 attempts × 6s). Typical rollout takes 3–5 min for both services.

## 7. Confirm

```bash
aws ecs describe-services --cluster ontology-retail-dev-cluster \
  --services ontology-retail-dev-api ontology-retail-dev-web --region $AWS_REGION \
  --query 'services[*].{name:serviceName,td:taskDefinition,running:runningCount,desired:desiredCount,deps:length(deployments)}'
```

Expected: `running == desired`, `deps == 1` (single deployment, prior ACTIVE drained).

## 8. Smoke verify

Direct ALB access is blocked by the SG (CloudFront prefix list only); verification goes via CloudFront with auth. Easiest path is opening `https://$PUBLIC_DOMAIN` (your CloudFront alias) in a browser, logged in as the demo user provisioned by `scripts/provision_cognito_users.sh`.

For headless verification of graph state (e.g. after a loader run), see [`reload-synthetic-data.md`](reload-synthetic-data.md) §5 "Verification".

---

## Troubleshooting

- **ECR push `denied: token expired`** → re-run step 2. See `ecr-auth-refresh.md`.
- **`services-stable` returns 255 (timeout)** → check CloudWatch logs `/aws/ecs/ontology-retail-dev/{api,web}` for the failing task. Common causes: syntax errors in newly added routers, missing env vars in task def, image manifest arch mismatch (x86 image on ARM64 task def).
- **New task starts then `deregisters`** → ALB health check (`/healthz`) failed. Check `/aws/ecs/ontology-retail-dev/api`; the task def's healthcheck path and grace period are in `infra-cdk/lib/compute-stack.ts`.
- **Need to roll back to a known-good revision** → `aws ecs update-service --task-definition ontology-retail-dev-api:N --force-new-deployment` with the prior `N`. Both services keep their last 5 revisions in ECS by default.

## See also

- [`reload-synthetic-data.md`](reload-synthetic-data.md) — when a code deploy needs a data refresh too.
- [`ecr-auth-refresh.md`](ecr-auth-refresh.md) — token expiry mid-deploy.
- [`incident-loader-rollback.md`](incident-loader-rollback.md) — if a loader run breaks the graph.
- `.claude/commands/deploy.md` — the same commands in slash-command form.
