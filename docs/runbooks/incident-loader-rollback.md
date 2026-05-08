# Runbook: Loader Incident Rollback

**When to use**: a `data.load` run produced unexpected graph state — wrong counts, missing edges, MalformedQueryException, or the demo UI shows obviously broken data after a reload. This runbook covers diagnosis + rollback.

**Pre-conditions**:
- You can identify roughly when the bad load ran (CloudWatch task ARN, S3 sync timestamp).
- Member-facing demo can tolerate ~10 min of restored-state rebuild time.

---

## 1. Confirm the incident

```bash
# Find the most recent loader task in CloudWatch
aws logs describe-log-streams \
  --log-group-name /aws/ecs/ontology-retail-dev/api \
  --order-by LastEventTime --descending --max-items 5 \
  --region ap-northeast-2 \
  --query 'logStreams[*].{name:logStreamName,lastEvent:lastEventTimestamp}'

# Read its tail
aws logs tail /aws/ecs/ontology-retail-dev/api \
  --log-stream-names api/api/<TASK_ID> --region ap-northeast-2 --since 1h
```

Look for: non-zero exit code, Python traceback, `MalformedQueryException`, anomalous entity counts (e.g. `members 0` when expected `1000`).

Run a graph sanity check (one-shot ECS task with Python `-c` against `neptunedata` — see `reload-synthetic-data.md` §5 for the pattern). Key sanity queries:

```cypher
MATCH (m:Member) RETURN count(m)              -- expect ~1000
MATCH (:Member)-[:LIVES_IN]->(:Region) RETURN count(*)  -- expect ~1000
MATCH (:Member)-[:MATCHES_PERSONA]->(:Persona) RETURN count(*)  -- expect ~1000
MATCH (p:Persona) RETURN count(p)             -- expect 45 (after Phase 2A spine bootstrap)
```

A wide miss on any of these confirms the incident.

---

## 2. Decide rollback strategy

| State | Strategy |
|---|---|
| Graph has wrong/stale data but loader code is fine | **Re-run with prior `data/output/`** (Strategy A) |
| Loader code itself is broken (e.g. new Cypher syntax error) | **Roll back task definition** to a prior known-good revision (Strategy B), then re-run loader |
| Graph is *partially* corrupted (some MERGEs ran, some failed) | **Targeted Cypher cleanup + re-run** (Strategy C) — most surgical |
| Total disaster (e.g. wrong account, prod data overwritten) | Restore Neptune from snapshot (Strategy D) — coordinate with platform team |

For 95% of incidents, Strategy A or B is enough.

---

## 3. Strategy A — restore prior `data/output/` from S3 versioning

If the synthetic-data S3 bucket has versioning on (it does, per `infra-cdk/lib/data-stack.ts`):

```bash
BUCKET=ontology-retail-dev-synthetic-data-061525506239

# List versions of e.g. members.json — pick a version older than the bad load
aws s3api list-object-versions \
  --bucket $BUCKET --prefix data/output/members.json \
  --region ap-northeast-2 \
  --query 'Versions[*].{version:VersionId,modified:LastModified}' \
  --max-items 10

# Copy a specific version back to "current" (this becomes the new latest)
aws s3api copy-object \
  --bucket $BUCKET \
  --copy-source "$BUCKET/data/output/members.json?versionId=<PRIOR_VERSION_ID>" \
  --key data/output/members.json --region ap-northeast-2

# Repeat for each affected file (transactions.json, touchpoints.json, etc.)
```

Then re-run the loader per `reload-synthetic-data.md` §3.

---

## 4. Strategy B — roll back task definition revision

If the loader code itself is broken and you need to roll back to a known-good revision:

```bash
# List recent revisions
aws ecs list-task-definitions --family-prefix ontology-retail-dev-api \
  --region ap-northeast-2 --sort DESC --max-items 5

# Re-run the loader using a prior revision (e.g. 27 if 28 is broken)
NETCFG=$(aws ecs describe-services --cluster ontology-retail-dev-cluster \
   --services ontology-retail-dev-api --region ap-northeast-2 \
   --query 'services[0].networkConfiguration' --output json)

aws ecs run-task --cluster ontology-retail-dev-cluster \
  --task-definition ontology-retail-dev-api:27 \
  --launch-type FARGATE \
  --network-configuration "$NETCFG" \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","data.load","--neptune","--from-s3"]}]}' \
  --region ap-northeast-2
```

> Rolling back the API service itself (not just the loader) requires `update-service --task-definition <prior-rev> --force-new-deployment` — see [`deploy-production.md`](deploy-production.md) §5.

---

## 5. Strategy C — targeted cleanup before re-run

For partial corruption (e.g. duplicate edges, orphan nodes), drop the problem subgraph and re-run.

**Examples**:

```cypher
-- Delete all DERIVED_FROM edges (then loader will re-MERGE them cleanly)
MATCH ()-[r:DERIVED_FROM]->() DELETE r

-- Delete all LIVES_IN edges (then loader Phase 2A-G re-MERGEs them)
MATCH ()-[r:LIVES_IN]->() DELETE r

-- Detach and delete all Members (nuclear; loader will re-create + reattach edges)
MATCH (m:Member) DETACH DELETE m
```

Run via the same one-shot ECS task pattern as the verifier, then re-run the loader. **All three of the above are safe to run idempotently** because the loader uses MERGE everywhere.

> **Never** run `MATCH (n) DETACH DELETE n` — that drops the entire graph including products / personas / regions, which require ~30 min to re-load.

---

## 6. Strategy D — Neptune snapshot restore (last resort)

```bash
# List automated snapshots
aws neptune describe-db-cluster-snapshots \
  --db-cluster-identifier ontology-retail-dev-neptune \
  --region ap-northeast-2 \
  --query 'DBClusterSnapshots[*].{id:DBClusterSnapshotIdentifier,created:SnapshotCreateTime,status:Status}'

# Restore (creates a NEW cluster — coordinate with infra; CDK does not auto-redirect)
aws neptune restore-db-cluster-from-snapshot \
  --db-cluster-identifier ontology-retail-dev-neptune-restore \
  --snapshot-identifier <SNAPSHOT_ID> \
  --engine neptune --region ap-northeast-2
```

This is **not zero-downtime** — restored cluster has a different endpoint, requiring CDK redeploy. Coordinate before invoking.

---

## 7. After rollback — re-verify

Run the same sanity checks from §1. Confirm Coverage map, Churn /map, Tier-up /map all return non-zero member counts when filtered by both spine (`per_camper`) and bridged narrative (`psn_001`) personas. If any return 0, the bridge or spine MERGE didn't materialize — see ADR-0005 + ADR-0006 for the expected state.

---

## See also

- [`reload-synthetic-data.md`](reload-synthetic-data.md) — happy-path loader runbook.
- [`deploy-production.md`](deploy-production.md) — task-definition revision management.
- [ADR-0005](../decisions/0005-narrative-spine-keyword-bridge.md), [ADR-0006](../decisions/0006-persona-spine-coexistence.md), [ADR-0007](../decisions/0007-member-region-distribution.md) — what the membership graph state should look like.
