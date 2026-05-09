---
name: cypher-conventions
description: Apply project-specific Cypher conventions for Amazon Neptune openCypher queries — keyword-only parameters, no f-string interpolation of user input, scalar coercion via `_flatten_props`. Use when writing, reviewing, or modifying Cypher in api/routers/, api/services/, or any module that calls neptune.open_cypher.
---

# Cypher Conventions for Neptune

Project memory captures three repeated Cypher gotchas. Apply these without exception.

## Rule 1 — `parameters` is keyword-only

The project wraps `boto3.neptunedata.execute_open_cypher_query` in `api/services/neptune.py`. Always pass parameters as keyword:

```python
# ✓ Correct
result = neptune.open_cypher(
    "MATCH (p:Product {id: $pid})-[:HAS_INGREDIENT]->(i) RETURN i.name AS name",
    parameters={"pid": product_id},
)

# ✗ Wrong — positional `parameters` raises TypeError
result = neptune.open_cypher(query, {"pid": product_id})
```

## Rule 2 — Never f-string user input

User-controlled strings must travel through `parameters`, never through f-string interpolation. F-string interpolation creates Cypher injection.

```python
# ✗ Injection risk
query = f"MATCH (p:Product) WHERE p.name CONTAINS '{user_query}' RETURN p"
neptune.open_cypher(query)

# ✓ Parameterized
query = "MATCH (p:Product) WHERE p.name CONTAINS $needle RETURN p"
neptune.open_cypher(query, parameters={"needle": user_query})
```

Even when the input *looks* trusted (a known persona ID, a SKU code from an internal catalog), parameterize it. The cost is zero and the discipline survives refactoring.

## Rule 3 — Coerce scalar properties via `_flatten_props`

Neptune returns property maps where scalar values are sometimes wrapped in single-element lists (vendor quirk depending on the openCypher path). Always pass node `properties()` through `api/services/neptune._flatten_props` before constructing Pydantic models:

```python
from api.services import neptune

rows = neptune.open_cypher("MATCH (p:Product) RETURN properties(p) AS props LIMIT 10").get("results", [])
products = [ProductRead(**neptune._flatten_props(row["props"])) for row in rows]
```

`_flatten_props` unwraps `[v]` → `v` for scalar single-element lists while preserving genuine list-typed properties (e.g., `categories`, `tags`).

## Rule 4 — F-string traps inside `{}` expressions

If you do build a query with f-string for a non-user, structural fragment (e.g., a label or relationship name from a static enum), never escape quotes inside the `{}` expression — Python 3.12 raises SyntaxError:

```python
# ✗ SyntaxError
query = f"MATCH (n:{config[\"label\"]}) RETURN n"

# ✓ Extract first
label = config["label"]
query = f"MATCH (n:{label}) RETURN n"
```

This is a frequent cause of stack traces during scenario additions; if you see `SyntaxError: f-string` while editing a router, this is the cause.

## When this skill applies

- Editing any `*.py` file under `api/routers/` or `api/services/`
- Reviewing diffs that touch `neptune.open_cypher`, `neptune.execute_open_cypher_query`, or any query string
- Writing new scenarios that pull from the knowledge graph
- When `code-reviewer` agent is invoked on a diff containing Cypher

## Outputs

When this skill applies to a diff or new code, emit a verdict block:

```
Cypher convention check: [PASS|FAIL]
Rules applied: [keyword-only-params, no-fstring-injection, flatten-props, fstring-trap]
Violations (if any):
  - <file>:<line> — <rule-name>: <one-line summary>
```

`[PASS]` means every Cypher call site in scope obeys all 4 rules. Each violation must cite the rule name from the rubric (rule-1 keyword-only, rule-2 no f-string, rule-3 flatten-props, rule-4 f-string traps) so downstream auto-fix tooling can route to the correct remediation.

## Related

- `data/load.py` — `_flatten_props` source (Neptune-bound scalar coercion used by the loader; query consumers should mirror its scalar discipline)
- `api/services/neptune.py` — the openCypher wrapper module (`open_cypher`, `subgraph_for_skus`, `_node_props`)
- `api/CLAUDE.md` — module conventions including SSE event vocabulary and Pydantic discipline
- Project memory: keyword-only `parameters` is a recurring gotcha that has bitten this project before
