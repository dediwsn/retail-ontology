# API Reference

All endpoints are mounted under `/api` and run on the FastAPI backend (`api/main.py`). CloudFront forwards `/api/*` to the API service via ALB; the rest goes to the Next.js web service.

Authentication: every request must carry the `id_token` cookie set by `/api/auth/callback`. Lambda@Edge enforces this for protected paths and 302-redirects unauthenticated viewers to Cognito Hosted UI.

SSE event vocabulary (shared across `/api/chat`, `/api/search/stream`, `/api/insights/stream`):

```
event: phase
data: {"name": "...", "ms": 123, "detail": "..."}

event: delta
data: {"text": "..."}

event: log
data: {"tool": "...", "input": {...}}

event: result | final | stop
data: {...}
```

## Auth

### `GET /api/auth/login`

302 redirect to Cognito Hosted UI. Used by the sidebar widget for explicit re-login.

### `GET /api/auth/callback?code=...`

OAuth code exchange; sets `id_token`, `access_token`, `refresh_token` HttpOnly cookies; redirects to `/`.

### `GET /api/auth/whoami`

Returns the active user's claims (`email`, `sub`, `username`) by decoding the `id_token` cookie. Returns 401 with `{"authenticated": false}` if no cookie is present. Drives the `SidebarAuth` widget.

### `GET /api/auth/logout`

Clears auth cookies and redirects to Cognito's hosted logout URL, which then bounces back to `/`.

## Scenarios

### `POST /api/search` (Scenario A)

Sync hybrid search with subgraph.

```json
{ "q": "임산부도 안전한 비건 토너", "top_k": 10, "persona": "p_001", "include_subgraph": true }
```

Response: `{ hits: SearchHit[], subgraph: Subgraph, query_echo: string }`.

### `POST /api/search/stream` (Scenario A)

Same input as `/api/search`. Returns SSE with phase events (`guardrail`, `embed`, `knn`, `bm25`, `rrf`, `rerank`, `subgraph`) followed by a `result` event with the full payload.

### `POST /api/chat` (Scenario B)

```json
{ "session_id": "sess_<uuid>", "message": "임신 6개월…", "actor_id": "p_001" }
```

Returns SSE with `log` (tool calls), `delta` (token text), and `stop` (final assembled answer) events.

### `POST /api/insights` (Scenario C)

```json
{ "q": "지난 4주간 20대 여성에게 검색 빈도가 급증한 성분 Top10", "period_days": 28 }
```

Response: `{ answer_ko: string, chart_spec: ChartSpec, drill_down_subgraph: Subgraph, chart_image_base64: string|null }`.

### `POST /api/insights/stream` (Scenario C)

Same input as `/api/insights`. Returns SSE with phase events (`neptune-agg`, `llm-start`, `llm-done`, `code-interpreter`, `drilldown`), `delta` events for the Sonnet token stream of `answer_ko`, and a `final` event with chart + subgraph.

### `POST /api/persona-match` (Scenario D)

```json
{ "persona_id": "p_001", "top_k": 10 }
```

Returns weighted SKU recommendations with HAS_CONCERN traversal explanations.

### `POST /api/safety/check` (Scenario E)

```json
{ "profile_id": "pregnant", "q": "토너", "domain": "beauty", "top_k": 10 }
```

Returns SKU list with safety classification (`safe`, `caution`, `avoid`) and ingredient hits.

### `POST /api/substitute` (Scenario F)

```json
{ "sku_id": "sku_xxx", "same_brand_ok": false, "top_k": 8 }
```

Returns same-category cross-brand alternatives with price delta.

### `POST /api/price/compare` (Scenario G)

```json
{ "q": "시카 진정 크림", "persona": "p_001", "top_k": 3 }
```

Returns top-K candidates each with a four-channel (CU / 이마트 / 올리브영 / 마컬) price/discount/stock matrix and persona-channel best-of recommendation.

### Scenario H · Logistics Network

#### `GET /api/logistics/network`

Full logistics network for the Korean map view: 17 sido + 34 sigungu regions, 30 warehouses (mfr/rdc/3pl/lastmile), 7 carriers, 76 routes (lanes).

#### `GET /api/logistics/warehouse/{wh_id}`

Warehouse detail — capacity, cold-chain flag, region label, inbound/outbound routes, recent 30 shipments.

#### `GET /api/logistics/events`

12 events (seasonal/promo/disaster/strike/outage) with affected regions and categories.

#### `GET /api/logistics/status`

KPI summary: active shipments, OTD rate, avg transit hours, exception count, active events, per-carrier breakdown. Drives the KPI strip on `/logistics`.

#### `GET /api/logistics/inventory/wh/{wh_id}?limit=100`

Inventory at one warehouse (default ordered by `on_hand_pallets` desc) with `days_of_cover`, capacity, temperature.

#### `GET /api/logistics/inventory/sku/{sku_id}?limit=50`

Inventory of one SKU across all warehouses — useful for "where do we have the most stock" queries.

#### `POST /api/logistics/nearest`

```json
{ "lat": 37.566, "lng": 126.978, "limit": 8, "types": ["rdc","3pl"], "cold_only": true }
```

Haversine k-NN over warehouses with optional type and cold-chain filters.

#### `GET /api/logistics/shortest-path?from_wh_id=wh_011&to_wh_id=wh_009`

BFS shortest path over Route edges (depth ≤ 4 — sufficient for the 30-warehouse network). Returns hop-by-hop list with route_id, carrier, distance, transit hours.

## Membership / Marketing (Scenarios I·J·K)

### `GET /api/churn/dashboard?top_k=30`

Scenario I — 이탈 위험 진단. Returns:
- `summary`: total members, high-risk count (≥0.7), VIP at-risk count, blended high-risk %, avg recency
- `top_at_risk`: top N members by churn_risk DESC then ltv_krw DESC (defaults to 30, max 100)
- `tier_breakdown`: per-tier rollup (total / at_risk / avg risk / avg LTV)
- `persona_breakdown`: per-persona rollup
- `recommended_winback`: campaigns where `type='winback'` with target personas
- `subgraph`: 10 highest-risk members + their tier + persona nodes (Cytoscape contract)

### `GET /api/churn/map?persona=<id>`

시도(region)별 이탈 위험 집계 — `/churn` 페이지의 *지도 탭* 백엔드. `Member.region_id`가 부여된 회원만 대상으로 17 시도 집계 (`members`, `at_risk` 회원수, `avg_churn_risk`, `avg_ltv_krw`). `persona`로 페르소나 슬라이스로 좁힐 수 있음. 코로플레스 색은 클라이언트가 `avg_churn_risk` 정규화로 결정.

### `GET /api/churn/member/{member_id}`

Scenario I drill-down. Returns the member's RFM, last 10 transactions, last 12 touchpoints, response_rate, persona-aware winback recommendation, and a 1-hop subgraph (member + tier + persona + last 5 tx + last 5 tp).

### `GET /api/acquisition/dashboard`

Scenario J — Campaign × Channel × Persona ROI. Returns:
- `summary`: total acquisition campaigns, total cost, attributed members + LTV, blended ROI, best channel
- `campaigns`: per-acquisition-campaign ROI (cost / attributed LTV from responded touchpoints)
- `channels`: per-channel rollup (kakao / push / email / sms)
- `persona_channel_matrix`: 5×5 cells with response rate per persona × channel, used for the heatmap

Attribution model is single-touch — a touchpoint with `responded=true` counts as attribution. Multi-touch attribution would not earn its keep on a 1k-member PoC.

### `GET /api/tier-up/dashboard?top_k=25`

Scenario K — Silver→Gold lift + upgrade candidates. Returns:
- `summary`: silver / gold cohort sizes, candidates count, avg candidate LTV
- `product_lift`: top N products by per-capita Gold-rate ÷ Silver-rate, half-step Laplace smoothed
- `category_lift`: same for Categories (top 15)
- `upgrade_candidates`: Silver members with LTV ≥ 1.5M, sorted by gap-to-Gold and surfaced with churn_risk + frequency

### `GET /api/tier-up/map?persona=<id>`

시도(region)별 등급 상승 후보 분포 — `/tier-up` 페이지의 *지도 탭* 백엔드. `Member.region_id`가 부여된 회원만 대상으로 17 시도 집계 (`silver_count`, `gold_count`, `candidate_count` = Silver 중 LTV ≥ `CANDIDATE_LTV_FLOOR`(1.5M), `avg_silver_ltv_krw`, `avg_gap_to_gold_krw`). `persona`로 페르소나 슬라이스 좁힘.

## Coverage Map (Scenario L)

### `GET /api/coverage/dashboard?persona=<id>&dimension=<count|churn|ltv|uncov>&radius_km=<int>`

Scenario L — 회원의 시도(sido)별 분포와 Warehouse 마커를 한국 지도에 겹쳐
"내 페르소나 회원 중 N km 안에 거점이 없는 비율"이라는 단일 KPI를 노출.

Query 파라미터:
- `persona` (optional) — 페르소나 ID(`per_pregnant` 등). 미지정 시 전체 회원 1,000명 대상.
- `dimension` (default `count`) — 코로플레스 색 결정용 클라이언트 힌트 (`count` 회원 수 / `churn` 평균 이탈위험 / `ltv` 평균 LTV / `uncov` 미도달 비율). 응답에는 4개 차원 원본 수치가 모두 들어 있어 토글 시 재호출 불필요.
- `radius_km` (default 80, range 10–300) — 도달권 임계.

응답:
- `summary`: total_members, covered_members, uncovered_members, coverage_pct, top_uncovered_region_*, persona meta
- `regions[]`: 17 시도 각각에 대해 region_code, name_ko, lat/lng, members, avg_churn_risk, avg_ltv_krw, tier_mix, nearest_warehouse_id/_km, covered
- `warehouses[]`: warehouse_id, name_ko, type, region_code, lat/lng

Coverage 판정은 시도 centroid → 가장 가까운 Warehouse haversine 거리 ≤ `radius_km`. Region centroid는 그래프 측 `r.lat`/`r.lng`가 있으면 사용, 없으면 in-code fallback dict (logistics-load 갭에 견고).

선행 조건: PR1에서 추가된 `Member.region_id` + `(Member)-[:LIVES_IN]->(Region)` 엣지가 적재되어 있어야 함. 없으면 전체 회원이 0명으로 집계됨.

## Knowledge Graph Object Explorer

### `GET /api/objects/{type}?limit=30`

Type slugs: `product`, `ingredient`, `concern`, `trend`, `brand`, `category`, `persona`, `channel`, `manufacturer`, `review`, `member`, `tier`, `campaign`, `transaction`, `touchpoint`.

Returns ranked list (per-type ordering — products by ingredient count, manufacturers by SKU count, reviews by helpful_count, etc.).

### `GET /api/objects/{type}/{id}`

Returns a single object's full properties + 1-hop subgraph (capped at 60 neighbors for high-fanout types like Channel).

## Ontology

### `GET /api/ontology/schema`

Returns 12 core classes with Korean labels, color codes, relations, and live Neptune node/edge counts. Drives the `/schema` ER diagram.

### `GET /api/ontology/standards`

Lists bundled mapping CSVs (`gs1-gpc-to-kfda-food.csv`, `inci-to-korean.csv`) with row counts.

### `GET /api/ontology/standards/{filename}?limit=500`

Returns columns + rows of the given CSV for the table browser.

### `GET /api/ontology/validation`

Coverage report — runs four checks (INCI, FoodOn, GS1↔KFDA, Channel-loader) and returns per-check `expected/covered/missing/severity` payload.

## Operations

### `GET /api/ops/ingest`

Neptune node/edge counts by label + OpenSearch document count.

### `GET /api/ops/guardrail?minutes=60&limit=40`

Recent CloudWatch log events tagged with `guardrail`.

### `GET /api/ops/memory?session_id=<id>&top_k=30`

AgentCore Memory short-term events for a given session, or empty snapshot keyed to the configured memory store if no session is provided.

### `GET /api/ops/eval?run=true|false`

30-query wow-search evaluation. Returns pass-rate and per-query result. `run=true` invokes a fresh batch (~30s); `run=false` returns the cached run (10-minute TTL).

### `GET /api/ops/trace?limit=50&session_id=<optional>`

In-process tool-call ring buffer (200 entries per API instance). Optional `session_id` filter.

### `GET /api/ops/cost?days=7`

Cost Explorer daily spend split by Bedrock / Neptune / OpenSearch with sparkline points. Returns an empty-shell + note if Cost Explorer is unavailable.

## Persona

### `GET /api/personas?limit=50`

40 synthetic personas with Korean labels and concern counts. Used by the global PersonaSwitch widget and the `/match` page.

## Health

### `GET /healthz`

Always-200 liveness probe consumed by ALB target-group health checks.
