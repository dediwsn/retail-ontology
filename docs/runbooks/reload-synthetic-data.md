# Runbook: Reload Synthetic Data into Neptune (and OpenSearch)

**When to use**: any change to `data/schemas.py`, `data/synthetic/*`, or `data/load.py`. Loader is **idempotent** (everything via `MERGE`), so it can be run any time without breaking existing nodes.

**Pre-conditions**:
- API task definition revision contains the loader code change (i.e., a fresh `docker push` + `register-task-definition` already happened — see [`deploy-production.md`](deploy-production.md)).
- Local `data/output/` is regenerated and synced to S3 (see step 2 below).
- You can resolve the latest API task definition revision.

---

## 1. Regenerate `data/output/` files locally

```bash
python3 -m data.synthetic.membership      # if changed: members + tiers + campaigns + transactions + touchpoints
python3 -m data.synthetic.logistics       # if changed: regions + warehouses + carriers + routes + shipments + events + inventory
python3 -m data.synthetic.personas        # if changed: personas.ndjson
python3 -m data.synthetic.products        # if changed: products.ndjson
python3 -m data.synthetic.reviews         # if changed: reviews.ndjson
```

`data/output/*.json` is `.gitignore`d — the loader pulls fresh files from S3 when run with `--from-s3`.

## 2. Sync to S3

```bash
aws s3 sync data/output/ \
  s3://ontology-retail-dev-synthetic-data-061525506239/data/output/ \
  --region ap-northeast-2 \
  --exclude "*" \
  --include "members.json" \
  --include "campaigns.json" \
  --include "transactions.json" \
  --include "touchpoints.json" \
  --include "tiers.json"
  # add --include for any other regenerated files
```

Use `--include` filters to push only what changed; full sync (no filters) is also safe — S3 does its own diff.

## 3. Run the one-shot ECS loader task

```bash
NETCFG=$(aws ecs describe-services --cluster ontology-retail-dev-cluster \
   --services ontology-retail-dev-api --region ap-northeast-2 \
   --query 'services[0].networkConfiguration' --output json)

# Find the latest task-def revision (must contain the loader code change!)
LATEST_REV=$(aws ecs describe-task-definition --task-definition ontology-retail-dev-api \
   --region ap-northeast-2 --query 'taskDefinition.revision' --output text)

aws ecs run-task --cluster ontology-retail-dev-cluster \
  --task-definition ontology-retail-dev-api:$LATEST_REV \
  --launch-type FARGATE \
  --network-configuration "$NETCFG" \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","data.load","--neptune","--from-s3"]}]}' \
  --region ap-northeast-2 \
  --query 'tasks[0].taskArn' --output text
```

Variants:
- `--neptune --opensearch --from-s3` to also re-index OpenSearch (slower, ~30 min for embeddings via Bedrock).
- `--neptune` (no `--from-s3`) if the data is already in `/app/data/output/` of the image (only true for the bundled commerce data — membership/logistics outputs are gitignored, so always use `--from-s3` for them).

## 4. Wait for completion

The loader takes **8–10 min** for a full membership reload (Neptune-only, ~25k Cypher round-trips at ~50ms each). Use:

```bash
TASK_ARN=<the arn from step 3>
aws ecs wait tasks-stopped --cluster ontology-retail-dev-cluster \
  --tasks $TASK_ARN --region ap-northeast-2
aws ecs describe-tasks --cluster ontology-retail-dev-cluster --tasks $TASK_ARN \
  --region ap-northeast-2 \
  --query 'tasks[0].{lastStatus:lastStatus,exitCode:containers[0].exitCode,reason:stoppedReason}'
```

> `aws ecs wait tasks-stopped` polls every 6s for 100 attempts (~10 min). If your loader runs longer, poll manually or extend with a `while`. Exit code 0 = clean success.

## 5. Verification

The loader's last log line prints entity counts:

```
manufacturers     30
brands            60
concerns          25
trends            30
personas          40
products         250
reviews         2480
derived_from_edges    10   # (after Phase 2A-G)
tiers              4
campaigns         20
members         1000
transactions    7862
touchpoints    10021
Done.
```

For deeper graph-state checks, run a one-shot Cypher verifier task. Replace the `command` override with a Python `-c` that calls `boto3.client('neptunedata').execute_open_cypher_query(...)`. Sample queries that confirm the membership layer is intact:

```cypher
-- Count of LIVES_IN edges (should equal Member count)
MATCH (:Member)-[:LIVES_IN]->(:Region) RETURN count(*) AS n

-- MATCHES_PERSONA count (should equal Member count if all members have persona_id)
MATCH (:Member)-[:MATCHES_PERSONA]->(:Persona) RETURN count(*) AS n

-- Spine personas (should be 5)
MATCH (p:Persona {is_spine: true}) RETURN p.persona_id AS pid ORDER BY pid

-- DERIVED_FROM bridge edges (should be 10 with the current keyword dict)
MATCH (:Persona)-[:DERIVED_FROM]->(:Persona) RETURN count(*) AS n

-- Camper top-3 region (verifies persona-biased distribution)
MATCH (m:Member)-[:LIVES_IN]->(r:Region)
WHERE (m)-[:MATCHES_PERSONA]->(:Persona {persona_id:"per_camper"})
RETURN r.region_code AS rc, r.name_ko AS ko, count(m) AS n
ORDER BY n DESC LIMIT 3

-- Phase 2B: External consumption layer (after Scenario M)
MATCH (i:IndustryCategory) RETURN count(i) AS n   -- expect 10
MATCH (:IndustryCategory)-[:OVERLAPS_WITH]->(:Category)
RETURN count(*) AS n                                -- expect ~43
MATCH (:Member)-[:HAS_CATEGORY_SPEND]->(:IndustryCategory)
RETURN count(*) AS n                                -- expect 10,410 (Q1+Q4)

-- Wallet-share spot check (Camper persona, Outdoor industry —
-- our_share should be 0% because outdoor has no GS1 OVERLAPS_WITH)
MATCH (m:Member)-[hcs:HAS_CATEGORY_SPEND {period: "2026-Q1"}]->(i:IndustryCategory {industry_id: "ind_outdoor"})
WHERE (m)-[:MATCHES_PERSONA]->(:Persona {persona_id: "per_camper"})
RETURN count(m) AS members, avg(hcs.amount_krw) AS avg_q_spend
-- expect ~190 members with avg_q_spend ~750k
```

Expected camper top-3: `경기 40 / 서울 37 / 강원 16` — 강원 is **over-indexed** vs the overall 4.3% (the 1.8× signal that confirms persona-biased synthesis is loaded correctly).

---

## Troubleshooting

- **Loader exits 0 but counts show 0 of some entity** → the relevant `*.json` wasn't synced to S3 in step 2. Verify with `aws s3 ls s3://ontology-retail-dev-synthetic-data-$AWS_ACCOUNT_ID/data/output/`.
- **Loader hangs at "Loading into Neptune…"** → Neptune cluster might be in a maintenance window or cold-start. Cluster status: `aws neptune describe-db-clusters --region ap-northeast-2 --query 'DBClusters[?DBClusterIdentifier==\`ontology-retail-dev-neptune\`].Status'`. Should be `available`.
- **Loader fails with `MalformedQueryException`** → newly added Cypher in `load.py` uses unsupported syntax for the deployed Neptune engine version. Avoid `EXISTS { MATCH ... }` subquery form; prefer pattern-expression `(a)-[:R]->(b)`. See ADR-0005 commentary.
- **`MATCHES_PERSONA` count is 0 after reload** → ensure the spine persona MERGE block ran. See `data/load.py` `_SPINE_PERSONAS`. If only some personas matched, check that `personas.ndjson` was actually synced.

## See also

- [`incident-loader-rollback.md`](incident-loader-rollback.md) — if the new loader produced unexpected graph state.
- [ADR-0007](../decisions/0007-member-region-distribution.md) — the persona-biased distribution this loader materializes.
- `data/CLAUDE.md` — loader conventions + entity types.
