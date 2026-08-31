# Diagrams

## `ontology-rag-llm.puml` / `.svg`

A sequence diagram of how the three layers — **ontology** (Neptune), **RAG**
(OpenSearch + Bedrock Knowledge Base), and **LLM** (Bedrock Sonnet 4.6) — call
each other at runtime. Traced from source, not from the architecture prose.

It covers the three paths that exercise all three layers differently:

| Path | Who leads | Role of each layer |
|---|---|---|
| **A — `/api/search`** | the retrieval pipeline | RAG retrieves, the **ontology explains** the result (1-hop subgraph). The LLM is used only for embedding, reranking and guardrails — it never writes prose. |
| **B — `/api/chat`** | the **LLM** | The model drives a tool-use loop; RAG, the ontology and memory are all just tools it may call. Up to 8 rounds. |
| **C — `/api/insights`** | the **ontology** | Aggregation runs *first*; the LLM only narrates numbers it was handed, and the prompt forbids inventing any. |

### Regenerating

PlantUML is the source of truth. If you have it installed:

```bash
plantuml -tsvg docs/diagrams/ontology-rag-llm.puml
```

This machine has neither Java nor `plantuml.jar`, so the committed SVG was
produced by a local renderer that supports the subset of PlantUML sequence
syntax this file uses:

```bash
python3 scripts/render_puml_sequence.py \
  docs/diagrams/ontology-rag-llm.puml \
  docs/diagrams/ontology-rag-llm.svg
```

Both routes read the same `.puml`. If you install PlantUML, prefer it and
delete the fallback renderer — it exists only to unblock this environment.

### Call-site index

Every message in the diagram maps to a real call site. Verify with:

| Diagram step | Source |
|---|---|
| `hybrid_search(q, top_k)` | `api/services/search.py:hybrid_search` |
| `ApplyGuardrail(INPUT/OUTPUT)` | `api/services/guardrails.py:apply` → `bedrock_runtime().apply_guardrail` |
| `InvokeModel cohere.embed-v4` | `api/services/embedding.py:_embed` (`input_type=search_query`) |
| two OpenSearch searches | `api/services/search.py` — `knn_body` and `bm25_body`; AOSS rejects the `hybrid` query plugin, hence two round trips |
| `_rrf_merge(..., k=60)` | `api/services/search.py:_rrf_merge` |
| `cohere.rerank-v3` + fallback | `api/services/search.py:_bedrock_rerank`, wrapped in `try/except` that falls back to RRF order |
| `subgraph_for_skus(top 5, hops=2)` | `api/services/neptune.py:subgraph_for_skus` — `$sku_ids` bound, path clause whitelisted via `_PATH_CLAUSES` |
| SSE `phase` / `delta` / `log` / `result` / `stop` | `api/routers/search.py:_sse`, `api/routers/insights.py:_sse`, `api/services/agent.py:converse_stream` |
| 8-round tool loop | `api/services/agent.py:converse_stream` — `for round_idx in range(8)` |
| 7 tool specs | `api/services/agent.py:TOOL_SPECS` |
| tool fan-out | `api/services/agent.py:_dispatch_tool` |
| `{ items, count }` wrapping | `api/services/agent.py` — Converse `toolResult.content[].json` must be an object, not an array |
| `_TRACE_BUF` ring buffer | `api/services/agent.py:_push_trace` (`deque(maxlen=200)`, per-instance) |
| `create_event` / `retrieve_memory_records` | `api/services/memory.py:save_event` / `retrieve_long_term` |
| `Retrieve(overrideSearchType=HYBRID)` | `api/services/kb.py:lookup` |
| Trend↔Ingredient aggregation | `api/routers/insights.py:_aggregate_trends` |
| `ConverseStream` + delta loop | `api/routers/insights.py:_bedrock_summarize` |
| deterministic fallback | `api/routers/insights.py:_bedrock_summarize` `except` branch |

### Two things the diagram deliberately shows as they are

1. **Scenario A's SSE `phase` events are progress markers, not timings.** They
   are emitted around a single `hybrid_search()` call; there is no per-stage
   instrumentation inside `services/search.py`. The router's own docstring says
   so.
2. **No matplotlib on the insights path.** `/api/insights` returns
   `chart_spec = { type, title, data[] }` and the client draws the bar chart.
   `api/services/code_interpreter.py` exists (156 lines, AgentCore Code
   Interpreter + NanumGothic) but **no router imports it** — verify with
   `grep -rn code_interpreter api/routers/`. The README and
   `docs/architecture.md` describe Code Interpreter as part of Scenario C;
   that is aspirational for the current code, not descriptive.
