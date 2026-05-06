# Phase 1 — Data Generation

Generates the synthetic dataset that backs scenarios A/B/C of the demo.

| Layer | What | Generation |
|---|---|---|
| **Public** | Categories (40), Ingredients (82 INCI), Nutrients (28) | Loaded from Phase 0 CSVs / hardcoded FoodOn subset |
| **Deterministic** | Manufacturers (30), Brands (60), Concerns (25), Trends (30), Channels (4) | `data/synthetic/deterministic.py` — pure Python, no LLM |
| **LLM-generated** | Personas (40, 5 wow + 35 synth), Products (250), Reviews (2,500) | `data/synthetic/{personas,products,reviews}.py` via Bedrock Claude Sonnet 4.6 |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r data/requirements.txt
```

## Run order

```bash
# 1. Deterministic — instant, no AWS
python -m data.synthetic.deterministic

# 2. Personas — 5 wow hardcoded + 35 LLM (~5 calls)
python -m data.synthetic.personas

# 3. Products — 250 SKUs (~32 LLM calls)
python -m data.synthetic.products

# 4. Reviews — 2,500 reviews (~100 LLM calls)
python -m data.synthetic.reviews
```

All LLM scripts support:
- `--dry-run`     — print plan + cost estimate, no Bedrock calls
- `--limit N`     — generate only N items (smoke test)
- `--no-resume`   — discard prior output and start fresh

Output lands in `data/output/` as JSON / NDJSON.

## AWS prerequisites

```bash
aws configure                                           # or AWS_PROFILE / IAM role
aws sts get-caller-identity                             # confirm
aws bedrock list-inference-profiles --region ap-northeast-2 \
  --query 'inferenceProfileSummaries[?contains(inferenceProfileName, `claude-sonnet-4-6`)]'
```

The default model is `global.anthropic.claude-sonnet-4-6` (cross-region inference profile, falls through APAC + global regions). Override:

```bash
export BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-6
export AWS_REGION=ap-northeast-2
```

## Cost estimate

At Sonnet 4.6 pricing (input $3 / output $15 per M tokens, Apr 2026):

| Stage | Calls | In tokens | Out tokens | Cost (USD) |
|---|---:|---:|---:|---:|
| Personas (35 LLM) | ~5 | ~30K | ~50K | ~$1 |
| Products (250) | ~32 | ~200K | ~500K | ~$8 |
| Reviews (2,500) | ~100 | ~500K | ~1.5M | ~$25 |
| **Total full batch** | **~137** | **~730K** | **~2.05M** | **~$34** |

Use `--limit` for smoke tests (e.g., `--limit 10` for ~$0.20).

## Output schema

All Pydantic models in `data/schemas.py`. NDJSON for streaming/append; one JSON object per line.

```bash
# Inspect
head -1 data/output/products.ndjson | python -m json.tool
wc -l data/output/*.ndjson
```

## Resume + idempotency

`personas.py` / `products.py` / `reviews.py` skip already-emitted IDs by default. Safe to interrupt with Ctrl-C and re-run.

## Wow tuning

5 personas (`psn_001..psn_005`) are hardcoded in `personas.py` to drive scenarios A/B/C. After generating products + reviews, run `data/synthetic/wow_tuning.py` (Phase 5 — to be added) to flip `is_wow=True` on the SKUs and reviews that match these personas' narratives.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ValidationError` skip rate >20% | Schema mismatch in tool spec | Adjust prompt or schema; rerun with `--no-resume` |
| `ThrottlingException` | Bedrock per-account quota | Smaller batch or sequential calls; or request quota increase |
| `AccessDeniedException` on `Converse` | Model access not enabled | Bedrock console → Model access → enable Anthropic models |
| Korean text quality off | Temperature too high | Lower to 0.6 in script |
