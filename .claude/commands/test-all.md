---
description: Run the full test surface (TS + Python AST + wow-query eval)
---

Execute the project's test surface in this order, stopping at first failure:

1. **TypeScript type-check**:
   ```bash
   cd web && npx tsc --noEmit
   ```

2. **Python syntax** (AST validate every router):
   ```bash
   .venv/bin/python -c "import ast, glob; [ast.parse(open(f).read()) for f in glob.glob('api/routers/*.py')]"
   ```

3. **Wow-query evaluation** (against the deployed API):
   ```bash
   python3 scripts/eval_wow_queries.py
   ```
   Target: pass-rate ≥85%, average latency <2s.

4. **Smoke test** the critical paths via CloudFront:
   ```bash
   # export PUBLIC_DOMAIN=retail-ontology.example.com  (your CloudFront alias)
   curl -fsS "https://$PUBLIC_DOMAIN/healthz"
   curl -fsS -X POST "https://$PUBLIC_DOMAIN/api/search" -H 'content-type: application/json' \
     -d '{"q":"시카 진정 크림","top_k":5}' | jq '.hits | length'
   ```

Report each step's outcome. If anything fails, surface the exact error and propose a fix.
