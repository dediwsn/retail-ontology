# Changelog

[![English](https://img.shields.io/badge/lang-English-blue.svg)](#english)
[![한국어](https://img.shields.io/badge/lang-한국어-red.svg)](#한국어)

---

# English

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — persona reaches Scenario F (substitute) and H (logistics)
- **F `/api/substitute`** accepts `persona` + `drop_persona_conflicts` (default true). Alternatives containing an ingredient the persona avoids are removed, preferred-ingredient matches earn `PERSONA_PREFERRED_BONUS = 4` (between a shared ingredient at 3 and a shared concern at 5), and `persona_preferred` / `persona_conflict` are returned per candidate. The persona pass runs across the whole 50-row candidate set **before** the `top_k` cut, so dropping a conflict promotes a real alternative instead of leaving a hole. `drop_persona_conflicts=false` flags conflicts instead of hiding them.
- Shared `services/search.py:persona_context()` extracted from `apply_persona_lens()` so A and F read the *same* avoid/prefer/favourite-brick facts — a product rejected as unsafe in search cannot reappear as a "substitute".
- **H `GET /api/logistics/network?persona=`** attaches `persona_member_count` to every `RegionOut` and `WarehouseOut` via the standard `MATCHES_PERSONA` OR `DERIVED_FROM` bridge pattern. `None` when no persona was supplied, `0` when asked and none live there — the map needs to tell "not asked" from "asked, nobody here". Overlay-query failure degrades to no overlay; the network always renders.
- Frontend: `substitute()` and `logisticsNetwork()` take an optional persona; `/substitute` and `/logistics` pages read `useActivePersona()` and re-fetch on change. Persona now re-slices **11 of 13** scenarios (A D E F G H I J K L M); B derives context from conversational memory and C is a deliberately persona-independent category rollup.
- 7 new tests in `tests/api/test_persona_substitute_logistics.py` (85 total).

### Fixed — persona lens on Scenario A + insights output guardrail
- **`SearchRequest.persona` was declared and never read.** The web client sent it (`api-client.ts`) and `PersonaSwitch` is mounted globally in `layout.tsx`, so the persona was transmitted and silently discarded — Scenario A results were identical for every persona. New `services/search.py:apply_persona_lens()` re-slices retrieved hits through the persona's ontology context: products carrying an avoided ingredient are dropped, products matching a preferred ingredient (`+0.15`) or favourite GS1 brick (`+0.08`) are boosted, and the reason is written into hit metadata (`persona_preferred` / `persona_favorite_category` / `persona_conflict`) so the UI can explain the re-ordering. Applied after retrieval, not as an OpenSearch filter — the prefer/avoid facts live in Neptune, and keeping retrieval persona-blind preserves the RAG-retrieves / ontology-explains split.
- Router over-fetches (`top_k * 2`, capped at 50) when a persona is active so the lens can drop hits and still return `top_k`. `/api/search/stream` emits an extra `persona` phase event after `rerank`.
- Neptune failure, an unknown persona, or a persona with no preferences all return the hits unchanged — the lens is an enhancement and never fails a search. Non-Product hits (reviews) pass through untouched.
- **`/api/insights` applied no guardrail at all**, despite the documented "Guardrails on chat input and insights output" contract. New `_guard_output()` applies the OUTPUT guardrail to the assembled answer in both the streaming and non-streaming endpoints, emitting a `guardrail` SSE event when it intervenes. Matches `services/agent.py`: deltas stream unscrubbed and the terminal event carries the authoritative text — a deliberate streaming trade-off, now documented rather than accidental. Never raises; degrades to the raw answer.
- 11 new tests in `tests/api/test_persona_lens.py` (78 total, was 67).

### Documentation — runtime trace corrections
- New `docs/diagrams/ontology-rag-llm.puml` + `.svg` — sequence diagram of the ontology / RAG / LLM interplay across Scenarios A, B and C, with a call-site index in `docs/diagrams/README.md`. Rendered by `scripts/render_puml_sequence.py` (no Java on the build host); `plantuml -tsvg` produces the same diagram from the same source.
- **Code Interpreter is not on the insights path.** `api/services/code_interpreter.py` is implemented but no router imports it; `/api/insights` returns a `chart_spec` derived from the Neptune aggregation and rendered client-side. README (EN + KR) and `docs/architecture.md` (EN + KR) corrected — they had described server-side matplotlib PNG rendering as active.
- `SECURITY.md` §2 rewritten: Lambda@Edge is not a pass-through (ADR-0012), and `_verify_jwt` already performs full RS256 + JWKS + iss/exp/aud verification. The remaining gap is `DEMO_PUBLIC_MODE` defaulting to `true`.
- New `docs/product/` — PRD, user stories, and a bilingual sales narrative.


### Added — Code Knowledge Graph (codegraph)
- New `/codegraph` page (Sidebar 메타 section) embedding the `graphify`-generated AST graph as a static iframe. **No LLM at build time** — graphify is an AST-only third-party skill, fully offline. Bundle ships in `web/public/codegraph/` (`graph.html` 1.3MB, `graph.json` 1.2MB, `manifest.json` 28KB, `GRAPH_REPORT.md` 44KB). Current snapshot: **1,751 nodes, 2,217 edges, 159 communities, 151 source files**.
- Fullscreen toggle (ESC to exit), per-node click-through into the graphify viewer, side links to raw `graph.html` / `graph.json` / `GRAPH_REPORT.md` for deeper exploration.
- 4-field per-community metadata via Bedrock Sonnet 4.6 (`scripts/label_codegraph_communities.py`): label / description / key_concepts / top_files. Stored in `community_meta.json` sidecar; `graph.html` patched in-place to display semantic labels (1,751 occurrences). Click-to-expand detail card in the page side-panel.
- Refresh workflow: `./scripts/refresh_codegraph.sh` (graphify update → bundle copy → Bedrock label → graph.html patch, ~3 min). Documented in [docs/runbooks/codegraph-refresh.md](docs/runbooks/codegraph-refresh.md).

### Documentation — Round 3 sync after Scenario M + v0.7.0 + codegraph
- All 7 CLAUDE.md files refreshed: scenario count `A–L` → `A–M`, router count 18→19 (`vip` added), entity counts include Phase 2B (10 IndustryCategory + 10,410 HAS_CATEGORY_SPEND + 43 OVERLAPS_WITH).
- `docs/architecture.md` gains §External Consumption (Phase 2B — Scenario M / VIP) and §Code Knowledge Graph (`/codegraph` — meta) subsections (EN + KR).
- `docs/api-reference.md` documents 4 missing VIP endpoints (whale / loyal / cross-category / trajectory) including the Loyal threshold-tuning history (commit `ae4df57`).
- `docs/membership.md` change-history table + 3 new rows (Phase 2B, Phase 2B 확장, codegraph meta).
- `README.md` features list expanded to 13 scenarios + codegraph meta + sidebar logo (EN + KR halves).
- New ADRs: 0008 (wallet-share VIP framework), 0009 (Phase 2B data model — IndustryCategory + OVERLAPS_WITH bridge), 0010 (codegraph community labelling via direct Bedrock), 0011 (sidebar configurable logo).
- New runbook: `codegraph-refresh.md`. `reload-synthetic-data.md` gains Phase 2B verification queries (HAS_CATEGORY_SPEND count = 10,410 etc.).
- IndustryCategory was registered in only 1 of 6 mandated locations through v0.7.0; round 3 closes the gap — `objects.py:_TYPE_REGISTRY`, `ontology.py:_CLASSES`/`_RELATIONS`, `web/app/objects/[type]/page.tsx:TYPE_META + LABEL_TO_SLUG`, and Sidebar 객체 탐색 all updated. Auto-sync rule in root CLAUDE.md strengthened to call out the 6-spot rule explicitly.

## [0.7.0] — 2026-05-08

3 commits expanding the project surface from 12 → 13 scenarios:
**Scenario M (VIP Target Builder)** with the Phase 2B external-consumption layer
plus 4 follow-up tabs landing the full 5-axis VIP matrix. Sidebar version
bumped `v0.5.0` → `v0.7.0`. New configurable company-logo button at sidebar
top, defaulting to AWS, click-cycles through presets for live demo swap.

### Added — Sidebar company logo (configurable, demo-friendly)
- New `web/components/CompanyLogo.tsx` button at sidebar top-right next to the version pill. **Default = AWS** (per `NEXT_PUBLIC_DEFAULT_LOGO_PRESET`, falls back to `aws`). Clicking cycles through 4 bundled presets (AWS / Demo Blue / Retail Demo Emerald / CPG Demo Violet) and persists the selection in `localStorage` (key `ontology-retail.company-logo`) — no rebuild needed for live demo swap.
- Adding a custom brand: drop your SVG into `web/public/logos/<id>.svg`, register the preset in `LOGO_PRESETS` in `CompanyLogo.tsx`. To make it the *default*, set `NEXT_PUBLIC_DEFAULT_LOGO_PRESET=<id>` in the web task-definition env block. See `web/public/logos/README.md`.

### Added — Scenario M tabs 2–5 (Loyal / Whale / Cross-category / Trajectory)
- **`GET /api/vip/whale`** — internal `tier=VIP` + `LTV ≥ ltv_floor_krw` (defaults 5M). Persona-aware. Lists Whale candidates with monetary, frequency, recency, churn_risk for retention prioritisation.
- **`GET /api/vip/loyal`** — Opportunity's mirror: `our_share ≥ share_floor` AND `total_spend ≥ total_floor_krw` per (Member, IndustryCategory). Defaults tuned to `share_floor=0.5` + `total_floor_krw=300_000` after the synthetic distribution analysis (median wallet share ≈ 0%, p90 ≈ 26%; the original 0.7/1M default produced 0 candidates — `ae4df57`). Surfaces members where we hold majority share — defensive marketing target. Slider lets the user dial up to 0.95 for stricter "dominant share" selection.
- **`GET /api/vip/cross-category`** — single-category internal buyers (`distinct_internal_cats=1`) whose external spend in *non-overlapping* industries exceeds `external_floor_krw`. Up-sell / cross-sell candidates: tells you which industry to extend each member into.
- **`GET /api/vip/trajectory`** — Q1/Q0 growth ratio ≥ `growth_floor` (default 1.2), `tier ≠ VIP`. Identifies "future VIPs" — members whose external + internal spend is rising fastest, ideal for early-upgrade campaigns.
- Phase 2B data layer extended: `external_spend.json` now contains both 2026-Q1 and 2025-Q4 periods (10,410 rows total = 2 × 5,205) — prior-quarter snapshot enables the Trajectory growth ratio. Per-member growth factor distribution: 25% strong (q1/q0 ≥ 1.5×) / 35% mild (1.18×–1.54×) / 30% flat / 10% declining.
- Scenario M page: 4 stub tabs replaced with full implementations sharing a generic `CandidatesTable<T>` component, `SliderControl`, `KpiCard`, and persona context. All 5 tabs respect the active PersonaSwitch persona.

### Added — Scenario M (VIP Target Builder + external consumption layer)
- New **Phase 2B external-consumption layer** in the synthetic data + graph: `IndustryCategory` nodes (10 industry-level categories — 스킨케어 / 메이크업 / 바디·선케어 / 음료·티 / 건강기능식품 / 영유아 식품 / 캠핑·BBQ 식품 / 일반 식료품 / 생활용품 / 캠핑 장비), `(IndustryCategory)-[:OVERLAPS_WITH]->(Category)` mapping to existing GS1 bricks (43 edges), and `(Member)-[:HAS_CATEGORY_SPEND {amount_krw, period}]->(IndustryCategory)` quarterly spend edges (10,410 = Q1 5,205 + Q4 5,205, persona-biased).
- New **`GET /api/vip/opportunity`** endpoint — wallet-share-aware "Opportunity VIP" identification. Joins external panel data with internal Transactions via the OVERLAPS_WITH bridge to compute `our_share = our_internal / (our_internal + external)` per (Member, IndustryCategory). Filters on `share_ceiling` + `total_floor_krw` + persona; returns ranked candidates with `untapped_krw` upside.
- New **Scenario M page (`/vip`)** with 5-tab structure — all 5 tabs (Opportunity / Loyal / Whale / Cross-category / Trajectory) fully implemented as of this release.
- `data/synthetic/external.py` — deterministic generator (SHA1 PRNG), persona × industry multipliers (camper×3.5 outdoor, pregnant×2.5 baby food, sensitive_skin×2.5 skincare, etc.).

### Changed
- Sidebar version `v0.5.0` → `v0.7.0`. `web/package.json` version field bumped to match.
- Sidebar header layout reflows to fit the new CompanyLogo button: `flex items-center justify-between` with truncating title block on the left.

### Documentation
- All seven CLAUDE.md files refreshed: scenario count `A–H` → `A–L`, router count `14` → `18`, entity counts include the membership layer (1,000 members + 4 tiers + 20 campaigns + 7,862 transactions + 10,021 touchpoints + 5 spine personas / 45 total).
- `docs/architecture.md` gains a Membership & Marketing layer section (EN + KR halves).
- `docs/api-reference.md` documents `GET /api/personas?segment_eligible=true`.
- `docs/membership.md` documents the `(narrative)-[:DERIVED_FROM]->(spine)` bridge in §2.2 and the new Phase 2A-G+ change-history row.
- `README.md` features list expanded to 12 scenarios (EN + KR).
- New ADRs: 0005 (narrative→spine keyword bridge), 0006 (persona spine/narrative coexistence), 0007 (member region distribution).
- New runbooks: `deploy-production.md`, `reload-synthetic-data.md`, `ecr-auth-refresh.md`, `incident-loader-rollback.md` (`docs/runbooks/` was previously empty).
- `tests/test_smoke.py` parametrize expanded from 15 to 18 routers (added `acquisition`, `churn`, `tier_up`).

## [0.5.0] — 2026-05-08

7 commits + AWS deploy (api task-def revision 28, web revision 28). Scenario surface
expanded 11 → 12 with the new map-based hub L. Membership data model gains a geographic
dimension and a narrative↔spine bridge that fixes a class of pre-existing persona-filter
bugs across scenarios I/J/K. Sidebar version bumped from `v0.2.0` → `v0.5.0`.

### Added — Scenario L (member-warehouse coverage hub)
- **Scenario L — Coverage Map** (회원-거점 커버리지). Persona-filtered choropleth of member distribution by 시도 + Warehouse markers + 4-dimension toggle (member count / avg churn / avg LTV / uncovered share) + radius slider. Single KPI "회원 중 N km 안에 거점 없는 비율" — the hub scenario that bridges membership · logistics · persona on one screen.
- `Member.region_id` + `(Member)-[:LIVES_IN]->(Region)` edge. Persona-biased KOSTAT 17-sido distribution: 임산부 → 수도권, 캠퍼 → 강원/경상, 4세맘 → 경기 신도시, 민감성피부 → 도시, 글루텐알레르기 → 균등. Camper persona over-indexes 강원 1.8× vs the overall average.
- `GET /api/coverage/dashboard?persona=&dimension=&radius_km=` — persona filter, all 4 dimensions in one response (no re-fetch on toggle), haversine-based reachability judgment.
- Map tabs on `/churn` and `/tier-up`. New `GET /api/churn/map?persona=` (per-region avg churn risk + at-risk count) and `GET /api/tier-up/map?persona=` (per-region Silver/Gold/candidate density + Gold-threshold gap) endpoints back them.

### Added — Persona spine ↔ narrative bridge
- 5-spine `Persona` nodes (`per_pregnant`, `per_kid_4yo_mom`, `per_camper`, `per_sensitive_skin`, `per_gluten_allergy`) MERGE'd at the head of `load_membership` with `is_spine=true`. Coexists non-destructively with the 40 narrative `psn_*` nodes — total Persona count 45.
- `(narrative:Persona)-[:DERIVED_FROM]->(spine:Persona)` keyword-bridge edges (10 edges from 9 narratives, multi-mapping supported — e.g. `psn_002` "워킹맘 (4세 글루텐알레르기)" links to both `per_kid_4yo_mom` and `per_gluten_allergy`).
- `GET /api/personas?segment_eligible=true` — filters to spine + bridged narratives only (~14 personas). Each item exposes `is_spine`, `is_bridged`, `bridge_targets` so the client can group / badge.

### Changed
- Scenario cards 11 → 12. Sidebar / home / guided-tour auto-synced per CLAUDE.md auto-sync rules.
- PersonaSwitch widget now calls `listPersonas` with `segment_eligible: true`, groups items as **5-spine 페르소나** (top, with SPINE badge) and **Narrative (bridged)**. Picking any visible persona is guaranteed to return non-zero members in map endpoints.
- Coverage / churn /map / tier-up /map routers use `MATCH (m:Member)-[:LIVES_IN]->(r:Region)` traversal (LIVES_IN edge as authoritative source for region) instead of property lookup, plus OR-pattern `(m)→spine OR (m)→spine←DERIVED_FROM←narrative` to accept both ID schemes.
- Sidebar version `v0.2.0` → `v0.5.0`. `web/package.json` version field bumped to match.
- `docs/membership.md` §8 "회원 위치 없음" limitation resolved; Phase 2A-G entry added to change history.

### Fixed
- `/coverage`, `/churn /map`, `/tier-up /map` returning **500 MalformedQueryException** under `?persona=` — Neptune's openCypher engine rejects the `EXISTS { MATCH ... }` subquery form. Switched to pattern-expression form `(m)-[:R]->(...)` (universally supported).
- All persona-filter queries returning **0 members** even when MATCHES_PERSONA edges should exist — root cause was the synthetic data using `per_*` IDs but `personas.ndjson` shipping only the 40 narrative `psn_*` nodes, so the loader's `MATCH (per:Persona {persona_id: $pid})` silently created 0 edges. Resolved by the spine MERGE + DERIVED_FROM bridge above.
- "**선택하면 회원수 0**" UX failure when picking any narrative persona on Coverage/Churn map/Tier-up map — narratives now resolve to one or more spines via DERIVED_FROM, and unmappable narratives are hidden from the picker via `segment_eligible=true`.

## [0.2.0] — 2026-05-01

22 commits over 24 hours — Phase 1 (graph density toggle) + Phase 2 (membership/marketing
layer with Scenarios I/J/K) + post-launch corrections (Sidebar wiring, Bedrock toolResult
shape fix, AgentCore Memory wire format, Cognito redirect_uri, ECR image push pipeline).
Sidebar version bumped from `v0.1` → `v0.2.0`.

### Added — Scenarios I·J·K (membership / marketing)
- Scenario I (`/churn` + `/api/churn/*`): RFM-based churn risk dashboard with per-tier / per-persona breakdowns, top-30 at-risk list, member drill-down (last txns + touchpoints + winback recommendation), Cytoscape 1-hop graph
- Scenario J (`/acquisition` + `/api/acquisition/dashboard`): per-campaign + per-channel ROI rollup with single-touch attribution, plus persona × channel response-rate heatmap
- Scenario K (`/tier-up` + `/api/tier-up/dashboard`): Silver→Gold cohort lift on products + categories with Laplace smoothing, plus upgrade-candidate list (Silver, LTV ≥1.5M)
- Three sidebar entries (badges I/J/K), three GuidedTour steps, three new API client functions

### Added — Membership data layer
- 5 new node types (`Member`, `MembershipTier`, `Campaign`, `Transaction`, `Touchpoint`) with 8 new edges (`BELONGS_TO`, `MATCHES_PERSONA`, `PREFERS_CHANNEL`, `MADE`, `OF_PRODUCT`, `HAS_TOUCHPOINT`, `FROM_CAMPAIGN`, `TARGETS`)
- `data/synthetic/membership.py` generates 1,000 members + 20 campaigns + ~7.8k transactions + ~10k touchpoints fully deterministically (SHA1 PRNG). First 3 members are reserved real-name fixtures (홍길동 / 김영희 / 최우형) for demo NL queries
- RFM-derived `churn_risk` and persona-tier correlations (임산부·아이맘 → high LTV, 캠퍼 → seasonal Silver)
- Loader wired into `data/load.py:load_neptune`; `_TYPE_REGISTRY` (objects router), `_CLASSES` + `_RELATIONS` (ontology router), `TYPE_META` (object explorer page), and Sidebar 객체 탐색 section all updated for the 5 new types

### Added — Agent capabilities
- 3 logistics tools in `api/services/agent.py:TOOL_SPECS`: `nearest_warehouses` (region_name → lat/lng resolution + haversine ranking + cold-only filter), `shortest_path` (Korean name → wh_id resolve + BFS over Route edges, max 4 hops), `inventory_lookup` (by wh_id or sku_id)
- 17-city Korean centroid map embedded in agent.py for instant region_name → coords resolution
- `agent.recent_traces()` 200-entry ring buffer + `_push_trace` from `converse_stream` tool dispatch — fixes prior 500 on `/api/ops/trace`

### Added — UX / streaming
- Density toggle (조밀 / 보통 / 넓게) on `CytoscapeView` — canvas-overlay button driving cose layout `nodeRepulsion` / `idealEdgeLength` / `gravity` for all 6 pages using the component
- Live phase strip on Search (BM25 / KNN / RRF / Bedrock rerank), Insights (Neptune / Sonnet 4.6), Chat (guardrail / memory / bedrock / tool:* / guardrail-out) — color-coded chips render incrementally as SSE phase events arrive
- 10 persona-tagged suggestion chips on chat empty state — auto-send on click, color-coded by persona (임산부/4세 아이/캠퍼/민감성/글루텐/계절성/멤버십)
- Chat conversation export — MD download (Blob, role headers + body + tool-call appendix) and PDF download (jsPDF + html2canvas, off-screen render at 760px → A4 paginated, lazy-imported ~250KB only on click)
- react-markdown v10 + remark-gfm rendering for chat / insights answers under shared `.chat-markdown` styles in globals.css; new `MarkdownView` component
- 11 scenario cards on home dashboard (A–K, color-coded) + Knowledge Graph object section (5 group sub-grids: 상거래 / 라이프스타일 / 리뷰·채널 / 물류·이벤트 / 멤버십)

### Added — API endpoints
- `GET /api/auth/login` (Cognito Hosted UI redirect helper) and `GET /api/auth/whoami` (id_token decode → claims)
- `POST /api/search/stream` and `POST /api/insights/stream` SSE variants emitting `phase` / `delta` / `result` events; `/api/insights/stream` now drives Bedrock Sonnet 4.6 `converse_stream` for live token streaming + 3-section MD-style answer
- 6 routers wired into `api/main.py` that lived as untracked working-tree code: `logistics, ops, persona_match, price, safety, substitute` — full scenario surface now reachable

### Changed — Layout / wiring
- Restored `516c38e`-era 4/28 dashboard layout via `tailwind.config.ts` `ink-50..950` + `accent-100..700` palette restore + Sidebar wiring in `app/layout.tsx` (left rail + main pane + top-right PersonaSwitch / GuidedTour widgets)
- Object Explorer collapsible inspector + breadcrumb header — graph canvas grows to ~95% width when 속성 접기 toggled; per-label sampling in detail Cypher (15 each / label) so Channel 1-hop shows Member + Product + Warehouse instead of Member-only top-60
- Object Explorer node tap → cross-type detail load via `LABEL_TO_SLUG` mapping; works for any 1-hop neighbour without URL navigation
- Object Explorer Transaction / Touchpoint friendly labels — synthesised from ts/amount/sku/channel/responded so the list shows `2026-04-15 · 35,000원 · sku_xxx` instead of opaque `tx_000123`
- Chat input form moved to TOP of section (matches search / insights pattern)

### Fixed
- Bedrock Converse `toolResult.content[].json` — array results from `semantic_search` / `kb_lookup` now wrapped as `{items, count}` so the model receives the data instead of throwing `ValidationException` mid-turn (was the actual root cause of "tool log only, no answer text")
- AgentCore Memory `create_event` wire format — `actorId` (not snake_case), `eventTimestamp` (UTC datetime), `payload` as list of conversational blocks. Failures swallowed so chat survives memory outages
- `/api/auth/callback` Host header dependency removed — CloudFront `Managed-AllViewerExceptHostHeader` policy strips Host before reaching ALB, so `redirect_uri` is now derived from the `PUBLIC_DOMAIN` env (infra-controlled) instead of the request Host
- `/api/objects/*` and `/api/ontology/*` routers were tracked but never wired into `main.py` → 404 on production. Added explicit `app.include_router()` calls
- API container Dockerfile missing `COPY ontology /app/ontology` — `_MAPPINGS_DIR` was nonexistent inside the container, causing `/api/ontology/standards` to return `[]` and `/api/ontology/validation` to flag every standard as 0% covered
- `data/load.py` was using `Optional[str]` without `from typing import Optional`. Caught by Kiro review-gate (PEP 563 saved it at runtime, but adding the import for static-checker correctness)
- `web/lib/api-client.ts` `personaMatch` / `substitute` / `priceCompare` passthroughs took a single `body` arg but pages called them with positional args — re-shape signatures to match call sites and build the proper request body
- Web build TS strict + ignoreBuildErrors flags + ESLint ignoreDuringBuilds in `next.config.mjs` — unblocks build while implicit-any cleanup happens incrementally
- Layout SSG prerender — wrap `{children}` in `<PersonaProvider>` so `useActivePersona()` doesn't throw at build time

## [0.1.0] — 2026-04-28

### Added — CI / testing harness
- Add `.github/workflows/ci.yml` — 4-job CI pipeline (`python-ast` compileall, `tsc-check` matrix [web, infra-cdk], `cdk-synth` + jest snapshot, `pytest`) on push/PR to main with concurrency cancel-in-progress
- Add `tests/` pytest suite — 28 tests in <1s: 16 router import smoke (`tests/test_smoke.py`) + 5 Pydantic model validation + 2 health + 5 `/api/search` integration with `httpx.AsyncClient` and boto3 mocked at the import-site (`tests/api/`)
- Add `tests/conftest.py` centralizing 18 dummy env vars at collection time + `DEMO_PUBLIC_MODE=true` + `REQUIRE_ORIGIN_AUTH=false` for ASGI-direct tests
- Add `infra-cdk/test/stacks.test.ts` — Jest snapshot tests for all 6 CDK stacks via `Template.fromStack().toJSON()` with deterministic test context (account `000000000000`); auto-generated 7727-line snapshot at `__snapshots__/stacks.test.ts.snap`
- Add `requirements-dev.txt` (pytest, pytest-asyncio, httpx) — dev-only, not installed in production Docker image
- Add `tests/CLAUDE.md` documenting test layout, conftest layering, ASGI fixture, mock-at-import-site convention, snapshot update flow
- Add 4 ADRs in `docs/decisions/` materializing session learnings: 0001 AgentCore Memory CDK AwsCustomResource pattern, 0002 CloudTrail L1 CfnTrail with manual bucket policy, 0003 Lambda@Edge stable-ID hardcoding, 0004 Cognito UserPoolClient CDK-only authoring
- Add `.claude/settings.json` (project-shared) — registers `PreToolUse` + `PostToolUse` + `Stop` hooks and a 60-entry `permissions.deny` covering MCP namespace bypass (`__delete_*`, `__execute_command`, serena `execute_shell_command`), CloudTrail audit-blinding (`delete-trail`, `stop-logging`), and the AWS IAM privilege-escalation triad (`attach-*-policy`, `create-policy-version`, `pass-role`)
- Add `.claude/hooks/scrub-secrets.sh` — PreToolUse + PostToolUse blocker for AKIA/ASIA, JWT, PEM private-key blocks, Slack tokens, GitHub PATs
- Add `.claude/hooks/changelog-reminder.sh` — Stop hook that flags structural file changes (api/routers, api/services, web/app/*/page.tsx, infra-cdk/lib/*-stack.ts, data/schemas.py, ontology/mappings/) without a CHANGELOG.md update
- Add `.claude/skills/wow-query-eval.md` — project-specific 30-query search quality gate skill with pre-flight checks
- Add `.claude/skills/cypher-conventions.md` — Neptune openCypher discipline (parameters keyword-only, no f-string interpolation, `_flatten_props` scalar coercion)
- Add `.claude/agents/{code-reviewer,security-auditor}.md` — `model: sonnet` pinned, structured `## Output format` section with severity taxonomy, finding shape, and termination phrase
- Add 5 module-level `CLAUDE.md` files now git-tracked (`api/`, `web/`, `data/`, `infra-cdk/`, `ontology/`) plus root `CLAUDE.md`
- Add `.harness-eval/` score history — 4 evaluations recorded (6.0/C → 5.5/D → 6.9/C → 7.9/B); README badge auto-updated
- Add Scenario H logistics network with Korean choropleth map (`react-simple-maps` + KOSTAT 17-sido GeoJSON), 30 warehouses, 76 lanes, KPI strip, and inline LLM chat panel
- Add Inventory as a first-class Knowledge Graph node — 940 rows, deterministic synthesis with cold-chain awareness; new `Inventory→Warehouse [HELD_AT]` and `Inventory→Product [OF_SKU]` edges
- Add logistics ontology classes — Region (51), Warehouse (30), Carrier (7), Route (76), Shipment (500), Event (12) — with edges `LOCATED_IN`, `OPERATES`, `FULFILLED_BY`, `FROM`/`TO`, `CARRIED_BY`, `VIA`, `CONTAINS`, `AFFECTS_REGION`, `AFFECTS_CATEGORY`
- Add three logistics LLM tools to the chat agent: `inventory_lookup`, `nearest_warehouses` (haversine k-NN), `shortest_path` (BFS over Route edges)
- Add logistics endpoints: `/api/logistics/{network,warehouse/...,events,status,inventory/wh/...,inventory/sku/...,nearest,shortest-path}`
- Add tabbed right panel on `/logistics` (거점·운송사 / 물류 도우미) so the LLM chat is visible by default instead of hidden behind a floating button
- Add Scenario G price/availability compare with four-channel matrix and persona-channel affinity weighting
- Add Manufacturer and Review object explorer types to the Knowledge Graph sidebar
- Add ontology validation report at `/validation` covering INCI/FoodOn/GS1+KFDA/Loader mappings
- Add operations trace viewer at `/ops/trace` with in-process tool-call ring buffer (200 events)
- Add global PersonaSwitch widget in the topbar that auto-injects active persona into search and chat APIs
- Add five-minute guided tour overlay walking through Scenarios A–G on first visit
- Add SSE streaming variant of `/api/search` with phase timeline (guardrail, embed, KNN, BM25, RRF, rerank, subgraph)
- Add SSE streaming variant of `/api/insights` with Sonnet token deltas and phase timeline (Neptune-agg, LLM, Code Interpreter, drilldown)
- Add Korean food ontology hydration (FoodOn → Korean alias map, 219 entries) at `ontology/mappings/foodon-to-korean.json`
- Add Channel→Product `AVAILABLE_IN` edges via deterministic `_assign_channels()` synthesis (CU/eMart/OliveYoung/Kurly)
- Add `/api/auth/whoami`, `/api/auth/login`, `/api/auth/logout` endpoints + sidebar footer login/logout widget
- Add custom domain `retail-ontology.whchoi.net` with ACM `*.whchoi.net` cert and Cognito callback registration

### Changed
- Convert `.claude/agents/*.yml` to `.md` with YAML frontmatter, pin `model: sonnet`, and add explicit `## Output format` section with severity taxonomy + finding shape + termination phrase
- Compact `.claude/settings.local.json` allow list 244 → 75 entries (-69%): consolidated 22 `tee /tmp/*-deploy*.log` paths to `Bash(tee /tmp/*)`, 9 awk one-shots to `Bash(awk *)`, 7 specific dig commands to `Bash(dig *)`, 17 hard-coded ALB/CloudFront curl probes to `Bash(curl -*)`, 12 `cdk deploy --require-approval never` permutations (already denied)
- Tighten `scripts/eval_wow_queries.py` threshold gate — `sys.exit(1)` at <85% pass rate (was warn-only at <70%); matches threshold declared in `.claude/commands/test-all.md`
- Align Conversational Agent UI structure with Search and Insights — input form lifted to top-level, sample chips moved below the form
- Restyle price compare result cards with consistent shading hierarchy (page → card → sub-card)
- Rename ontology relation `Channel → Product STOCKS` to `Product → Channel AVAILABLE_IN` to match loader semantics

### Fixed
- Fix `priceCompare` 500 error caused by passing `parameters` as a positional argument to `neptune.open_cypher`
- Fix `insights/stream` SyntaxError from escaped quotes inside f-string expressions
- Fix INCI validation false negatives by slugifying CSV `inci_name` to match Neptune `inci:<slug>` IDs
- Fix GS1/KFDA validation by filtering Neptune categories to food domain only (beauty bricks are out of scope for the food CSV)
- Fix `boto_session.client(...)` invocation in `/ops/cost` to call the factory function before `.client()`
- Fix dead ADR link in `docs/architecture.md` line 124 (referenced nonexistent `0001-single-image-two-roles.md`); cross-link the four real ADRs
- Fix duplicated `whoami`/`logout` endpoint blocks in `docs/api-reference.md` (cosmetic merge artifact)

### Removed
- Remove cost monitor from the operations sidebar (endpoint retained but not surfaced)

## [0.1.0] - 2026-04-27

### Added
- Add real Lambda@Edge cookie authentication and Cognito callback handler
- Add 30 wow-query evaluation harness with pass-rate scoreboard at `/ops/eval`
- Add CloudTrail management-event logging and ALB access logs
- Add Cost Anomaly subscription on Default-Services-Monitor
- Add Cognito user pool with provisioning script for demo accounts
- Add Bedrock Knowledge Base with hybrid search (BM25 + KNN + Reranker)
- Add AgentCore Memory short-term and long-term namespaces
- Add Code Interpreter sandbox for Korean-glyph matplotlib charts
- Add seven baseline scenarios A–F (semantic search, chat, insights, persona match, safety, substitute) plus knowledge-graph object explorer

### Changed
- **BREAKING:** Switch chat and insights model from Haiku Lite to Sonnet 4.6 across all Bedrock Converse calls
- Cache origin auth secret with five-minute TTL to limit Secrets Manager call volume

### Fixed
- Fix reranker fallback when the cross-region inference profile is unavailable
- Fix AOSS bulk indexing to surface per-document errors and use auto-generated `_id`
- Fix Edge Stack CFN dynamic reference and Neptune `_flatten_props` scalar coercion
- Fix Neptune client to use `boto3.neptunedata` instead of manual SigV4 signing
- Fix JWKS lookup with TTL cache and constant-time origin token comparison
- Fix Neptune IAM action to `neptune-db:*` wildcard (specific actions returned 403)
- Fix CloudTrail subscription to management-event type only

### Security
- Rotate origin shared secret to Secrets Manager and verify Cognito JWTs with RS256
- Wire AuthMiddleware into FastAPI main entry point
- Tighten CORS allow-list and document password rotation policy
- Scope AgentCore Memory IAM to least privilege and relax Cognito password to eight characters for demo accounts
- Remove account-root policy from OpenSearch and use portable cost monitor lookup

[Unreleased]: https://github.com/whchoi98/ontology-retail/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/whchoi98/ontology-retail/releases/tag/v0.1.0

---

# 한국어

이 프로젝트의 모든 주요 변경 사항은 이 파일에 기록됩니다.
이 문서는 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)를 기반으로 하며,
[Semantic Versioning](https://semver.org/spec/v2.0.0.html)을 따릅니다.

## [Unreleased]

### Added — 페르소나가 시나리오 F(대체재)와 H(물류)까지 확장
- **F `/api/substitute`**가 `persona` + `drop_persona_conflicts`(기본 true)를 받습니다. 페르소나가 회피하는 성분이 든 대안은 제거되고, 선호 성분 일치는 `PERSONA_PREFERRED_BONUS = 4`(공유 성분 3과 공유 관심사 5 사이) 가점을 받으며, 후보마다 `persona_preferred` / `persona_conflict`가 반환됩니다. 페르소나 패스는 `top_k` 컷 **이전**에 50행 후보 전체에 적용되므로, 충돌 후보를 빼면 빈자리가 남는 대신 실제 대안이 올라옵니다. `drop_persona_conflicts=false`면 숨기지 않고 플래그만 답니다.
- `apply_persona_lens()`에서 공용 `services/search.py:persona_context()`를 추출 — A와 F가 **동일한** 회피/선호/선호브릭 사실을 읽으므로, 검색에서 위험으로 걸러진 상품이 "대체재"로 되살아날 수 없습니다.
- **H `GET /api/logistics/network?persona=`**가 표준 `MATCHES_PERSONA` OR `DERIVED_FROM` 브리지 패턴으로 모든 `RegionOut` · `WarehouseOut`에 `persona_member_count`를 붙입니다. 페르소나 미지정 시 `None`, 지정했으나 해당 지역에 회원이 없으면 `0` — 지도는 "묻지 않음"과 "물었는데 없음"을 구분해야 합니다. 오버레이 쿼리 실패 시 오버레이 없이 degrade 하며, 네트워크는 항상 렌더링됩니다.
- 프론트엔드: `substitute()` · `logisticsNetwork()`가 선택적 페르소나를 받고, `/substitute` · `/logistics` 페이지가 `useActivePersona()`를 읽어 변경 시 재조회합니다. 이제 페르소나가 **13개 중 11개** 시나리오(A D E F G H I J K L M)를 다시 자릅니다. B는 대화 메모리로 맥락을 잇고, C는 의도적으로 페르소나에 종속되지 않는 카테고리 집계입니다.
- `tests/api/test_persona_substitute_logistics.py`에 7개 테스트 추가 (총 85개).

### Fixed — 시나리오 A 페르소나 렌즈 + 인사이트 출력 가드레일
- **`SearchRequest.persona`가 선언만 되고 읽히지 않았습니다.** 웹 클라이언트는 값을 보내고(`api-client.ts`) `PersonaSwitch`는 `layout.tsx`에 전역 마운트되어 있었으므로, 페르소나는 전달된 뒤 조용히 버려졌습니다 — 시나리오 A 결과가 모든 페르소나에서 동일했습니다. 새 `services/search.py:apply_persona_lens()`가 검색 결과를 페르소나의 온톨로지 컨텍스트로 다시 자릅니다: 회피 성분을 가진 상품은 제외, 선호 성분(`+0.15`) 또는 선호 GS1 브릭(`+0.08`) 일치 상품은 가점, 그리고 그 이유를 메타데이터(`persona_preferred` / `persona_favorite_category` / `persona_conflict`)에 기록해 UI가 재정렬을 설명할 수 있게 했습니다. OpenSearch 필터가 아니라 검색 **이후**에 적용 — 선호/회피 사실은 Neptune에 있고, 검색 단계를 페르소나-블라인드로 두어야 "RAG가 찾고 온톨로지가 설명한다"는 분업이 유지됩니다.
- 페르소나가 있을 때 라우터가 `top_k * 2`(최대 50)로 over-fetch 하여, 렌즈가 결과를 제외해도 `top_k`를 채웁니다. `/api/search/stream`은 `rerank` 다음에 `persona` phase 이벤트를 추가로 방출합니다.
- Neptune 장애, 알 수 없는 페르소나, 선호 정보가 없는 페르소나는 모두 입력을 그대로 반환합니다 — 렌즈는 부가 기능이며 검색을 실패시키지 않습니다. Product가 아닌 결과(리뷰)는 그대로 통과합니다.
- **`/api/insights`에 가드레일이 전혀 적용되지 않고 있었습니다.** 문서화된 "챗 입력 + 인사이트 출력 가드레일" 계약과 어긋난 상태였습니다. 새 `_guard_output()`이 스트리밍/비스트리밍 양쪽에서 완성된 답변에 OUTPUT 가드레일을 적용하고, 개입 시 `guardrail` SSE 이벤트를 방출합니다. `services/agent.py`와 동일한 패턴 — delta는 스크럽 없이 흐르고 종료 이벤트가 정본을 전달하는 스트리밍 트레이드오프를, 이제 우연이 아니라 문서화된 선택으로 둡니다. 예외를 던지지 않고 원문으로 degrade 합니다.
- `tests/api/test_persona_lens.py`에 11개 테스트 추가 (총 78개, 기존 67개).

### Documentation — 런타임 추적 기반 수정
- 신규 `docs/diagrams/ontology-rag-llm.puml` + `.svg` — 시나리오 A·B·C 전반의 온톨로지 / RAG / LLM 상호작용 시퀀스 다이어그램, 호출 지점 색인은 `docs/diagrams/README.md`. 빌드 호스트에 Java가 없어 `scripts/render_puml_sequence.py`로 렌더링했으며, 같은 소스에서 `plantuml -tsvg`도 동일한 다이어그램을 생성합니다.
- **Code Interpreter는 인사이트 경로에 없습니다.** `api/services/code_interpreter.py`는 구현되어 있으나 어떤 라우터도 import 하지 않으며, `/api/insights`는 Neptune 집계에서 파생한 `chart_spec`을 반환하고 클라이언트가 렌더링합니다. README(EN+KR)와 `docs/architecture.md`(EN+KR)를 수정 — 서버측 matplotlib PNG 렌더링이 동작 중인 것처럼 서술되어 있었습니다.
- `SECURITY.md` §2 재작성: Lambda@Edge는 pass-through가 아니며(ADR-0012), `_verify_jwt`는 이미 완전한 RS256 + JWKS + iss/exp/aud 검증을 수행합니다. 남은 격차는 `DEMO_PUBLIC_MODE` 기본값 `true`입니다.
- 신규 `docs/product/` — PRD, 사용자 스토리, 이중 언어 세일즈 내러티브.


### 추가 — 코드 지식 그래프 (codegraph)
- 신규 `/codegraph` 페이지 (사이드바 메타 섹션) — `graphify`가 생성한 AST 그래프를 정적 iframe으로 임베드. **빌드 시 LLM 호출 0** — graphify는 AST-only 서드파티 스킬, 오프라인 동작. 정적 자산은 `web/public/codegraph/` 에 번들. 현재 스냅샷: **1,751 노드, 2,217 엣지, 159 커뮤니티, 151 소스 파일**.
- 전체화면 토글 (ESC 해제), graphify 뷰어 내 노드 클릭 탐색, raw `graph.html`/`graph.json`/`GRAPH_REPORT.md` 직접 링크.
- 4-필드 per-community 메타데이터 — Bedrock Sonnet 4.6의 구조화 JSON 출력 (`scripts/label_codegraph_communities.py`): label / description / key_concepts / top_files. `community_meta.json` sidecar에 저장; `graph.html` 1,751건 in-place 패치하여 의미 라벨 표시. 페이지 사이드 패널에 클릭-펼쳐보기 상세 카드.
- 갱신 워크플로: `./scripts/refresh_codegraph.sh` (graphify update → bundle copy → Bedrock 라벨 → graph.html 패치, ~3분). [docs/runbooks/codegraph-refresh.md](docs/runbooks/codegraph-refresh.md) 참조.

### 문서 — Round 3 sync (시나리오 M + v0.7.0 + codegraph 반영)
- 7개 CLAUDE.md 파일 전체 새로고침 — 시나리오 카운트 `A–L` → `A–M`, 라우터 18→19 (`vip` 추가), 엔티티 카운트에 Phase 2B 포함 (10 IndustryCategory + 10,410 HAS_CATEGORY_SPEND + 43 OVERLAPS_WITH).
- `docs/architecture.md` 에 §External Consumption (Phase 2B — Scenario M / VIP) + §Code Knowledge Graph (`/codegraph` — meta) 서브섹션 추가 (EN + KR).
- `docs/api-reference.md` 에 누락된 VIP 4개 엔드포인트 (whale / loyal / cross-category / trajectory) 문서화. Loyal 임계 튜닝 이력(`ae4df57`) 포함.
- `docs/membership.md` 변경 이력에 3개 row 추가 (Phase 2B, Phase 2B 확장, codegraph 메타).
- `README.md` features 목록을 13 시나리오 + codegraph 메타 + 사이드바 로고로 확장 (EN + KR).
- 신규 ADR 4건: 0008 (wallet-share VIP 프레임워크), 0009 (Phase 2B 데이터 모델 — IndustryCategory + OVERLAPS_WITH 브릿지), 0010 (codegraph community 라벨링 via 직접 Bedrock), 0011 (사이드바 설정 가능 로고).
- 신규 runbook: `codegraph-refresh.md`. `reload-synthetic-data.md` 에 Phase 2B 검증 쿼리 추가 (HAS_CATEGORY_SPEND 10,410 등).
- v0.7.0 시점에 IndustryCategory가 6개 등록 위치 중 1곳에만 등록되어 있었음. Round 3에서 갭 해소 — `objects.py:_TYPE_REGISTRY`, `ontology.py:_CLASSES`/`_RELATIONS`, `web/app/objects/[type]/page.tsx:TYPE_META + LABEL_TO_SLUG`, Sidebar 객체 탐색 모두 업데이트. 루트 CLAUDE.md auto-sync 규칙도 *6-spot 명시*로 강화.

## [0.7.0] — 2026-05-08

3 커밋, 시나리오 12 → 13 확장: **시나리오 M (VIP 타깃 빌더)** + Phase 2B 외부 소비 레이어
+ 4개 후속 탭 풀 구현. 사이드바 버전 `v0.5.0` → `v0.7.0`. 사이드바 상단에 *설정 가능한*
회사 로고 버튼 신규 — 기본 AWS, 클릭으로 프리셋 순환하여 데모 중 *실시간 교체* 가능.

### 추가 — 사이드바 회사 로고 (설정 가능, 데모 친화)
- 신규 `web/components/CompanyLogo.tsx` 버튼이 사이드바 상단 우측, 버전 pill 옆에 표시. **기본값 = AWS** (`NEXT_PUBLIC_DEFAULT_LOGO_PRESET` 환경변수, 미설정 시 `aws`). 클릭하면 4개 번들 프리셋(AWS / Demo Blue / Retail Demo Emerald / CPG Demo Violet)을 순환하며 `localStorage` (`ontology-retail.company-logo`)에 저장 — *재배포 없이 라이브 데모 교체* 가능.
- 커스텀 브랜드 추가: `web/public/logos/<id>.svg` 에 SVG 드롭, `CompanyLogo.tsx` 의 `LOGO_PRESETS` 에 한 줄 등록. *기본값* 으로 만들려면 web task-definition 환경변수 `NEXT_PUBLIC_DEFAULT_LOGO_PRESET=<id>`. 자세한 가이드는 `web/public/logos/README.md`.

### 추가 — 시나리오 M 탭 2~5 (Loyal / Whale / Cross-category / Trajectory)
- **`GET /api/vip/whale`** — `tier=VIP` + `LTV ≥ ltv_floor_krw` (기본 5M). 페르소나 필터. retention 우선순위용 monetary/frequency/recency/churn_risk 동반.
- **`GET /api/vip/loyal`** — Opportunity의 거울: `our_share ≥ share_floor` AND `total_spend ≥ total_floor_krw` (회원 × 카테고리) 식별. 합성 분포 분석(median wallet share ≈ 0%, p90 ≈ 26%) 후 기본값 `share_floor=0.5` + `total_floor_krw=300_000` 으로 튜닝 (초기 0.7/1M은 0건이라 — `ae4df57`). 슬라이더로 0.95까지 상향해 *압도적 점유* 좁힘 가능.
- **`GET /api/vip/cross-category`** — 우리에게 1개 카테고리만 거래하는 회원 (`distinct_internal_cats=1`) + 그 회원의 *다른 industry* 외부 지출이 `external_floor_krw` 이상. up-sell/cross-sell 후보, 어느 industry로 확장할지 직접 알려줌.
- **`GET /api/vip/trajectory`** — Q1/Q0 성장률 ≥ `growth_floor` (기본 1.2), `tier ≠ VIP`. *잠재 VIP* 식별 — 외부+내부 지출이 가장 빠르게 상승 중인 회원, 조기 격상 캠페인 ROI 최고.
- Phase 2B 데이터 레이어 확장: `external_spend.json` 가 이제 2026-Q1과 2025-Q4 두 분기를 모두 포함 (10,410 rows = 2 × 5,205). 회원별 성장 분포: 25% 강성장(q1/q0 ≥ 1.5×) / 35% 약성장(1.18×–1.54×) / 30% flat / 10% 하락.
- 시나리오 M 페이지: 4개 stub 탭이 모두 풀 구현으로 교체. 5개 탭이 공통 `CandidatesTable<T>` + `SliderControl` + `KpiCard` 컴포넌트 + 페르소나 컨텍스트 공유.

### 추가 — 시나리오 M (VIP 타깃 빌더 + 외부 소비 레이어)
- 신규 **Phase 2B 외부 소비 레이어** (합성 데이터 + 그래프): `IndustryCategory` 노드 10종 (스킨케어 / 메이크업 / 바디·선케어 / 음료·티 / 건강기능식품 / 영유아 식품 / 캠핑·BBQ 식품 / 일반 식료품 / 생활용품 / 캠핑 장비), `(IndustryCategory)-[:OVERLAPS_WITH]->(Category)` 기존 GS1 brick 매핑 (43건), `(Member)-[:HAS_CATEGORY_SPEND {amount_krw, period}]->(IndustryCategory)` 분기별 지출 엣지 (10,410 = Q1 5,205 + Q4 5,205, 페르소나 편향).
- 신규 **`GET /api/vip/opportunity`** — wallet-share 기반 Opportunity VIP 식별. 외부 패널 데이터와 내부 Transaction을 OVERLAPS_WITH 브릿지로 조인하여 (Member, IndustryCategory)당 `our_share = our_internal / (our_internal + external)` 계산. `share_ceiling` + `total_floor_krw` + 페르소나로 필터링하고 `untapped_krw`(미점유 금액) 함께 반환.
- 신규 **시나리오 M 페이지 (`/vip`)** — 5-탭 구조, 0.7.0 시점에는 *5개 탭 모두 풀 구현* 완료.
- `data/synthetic/external.py` — 결정론적 generator (SHA1 PRNG), persona × industry multiplier (camper×3.5 outdoor, pregnant×2.5 영유아, sensitive_skin×2.5 스킨케어 등).

### 변경
- 사이드바 버전 `v0.5.0` → `v0.7.0`. `web/package.json` version 필드 동기.
- 사이드바 헤더 layout 재구성 — `flex justify-between` 으로 좌측 타이틀(truncate) + 우측 신규 CompanyLogo 버튼 배치.

### 문서
- 7개 CLAUDE.md 파일 전체 동기화 — 시나리오 카운트 `A–H` → `A–L`, 라우터 `14` → `18`, 엔티티 카운트에 멤버쉽 레이어 반영 (1,000 회원 + 4 등급 + 20 캠페인 + 7,862 거래 + 10,021 접점 + 5 spine 페르소나 / 총 45).
- `docs/architecture.md` 에 Membership & Marketing 레이어 섹션 추가 (EN + KR 양쪽).
- `docs/api-reference.md` 에 `GET /api/personas?segment_eligible=true` 문서화.
- `docs/membership.md` §2.2 에 `(narrative)-[:DERIVED_FROM]->(spine)` 브릿지 + Phase 2A-G+ 변경 이력 추가.
- `README.md` 시나리오 목록 12개로 확장 (EN + KR).
- 신규 ADR 3건: 0005 (narrative→spine keyword 브릿지), 0006 (페르소나 spine/narrative 공존), 0007 (회원 지역 분포).
- 신규 runbook 4건: `deploy-production.md`, `reload-synthetic-data.md`, `ecr-auth-refresh.md`, `incident-loader-rollback.md` (`docs/runbooks/` 가 비어 있었음).
- `tests/test_smoke.py` parametrize 가 15 → 18 라우터로 확장 (`acquisition`, `churn`, `tier_up` 추가).

## [0.5.0] — 2026-05-08

7 커밋 + AWS 배포 (api task-def revision 28, web revision 28). 시나리오 표면 11 → 12개로
확장 (지도 기반 허브 L 신규). 멤버쉽 데이터 모델에 *지리적 차원*과 *narrative ↔ spine
브릿지*가 추가되어 시나리오 I/J/K의 *사전부터 존재하던 페르소나 필터 0명 버그*가 해결됨.
사이드바 버전 `v0.2.0` → `v0.5.0`.

### 추가 — 시나리오 L (회원-거점 커버리지 허브)
- **시나리오 L — 회원-거점 커버리지 지도**. 페르소나 컨텍스트로 필터링된 회원의 시도별 분포(코로플레스) + Warehouse 마커 + 4 차원 토글(회원 수 / 평균 이탈 / 평균 LTV / 미도달 비율) + radius 슬라이더. KPI 하나 — "내 페르소나 회원 중 N km 안에 거점 없는 비율" — 을 우상단에 노출하여 멤버쉽·물류·페르소나를 한 화면에서 직조하는 *허브* 시나리오.
- `Member.region_id` + `(Member)-[:LIVES_IN]->(Region)` 엣지. KOSTAT 17 시도 인구 baseline에 페르소나별 multiplier(임산부=수도권, 캠퍼=강원/경상, 4세맘=경기 신도시, 민감성피부=도시, 글루텐알레르기=균등)를 곱한 weighted pick. 1,000명 기준 강원 비율이 캠퍼 페르소나에서 7.7% vs 전체 4.3% (~1.8× over-index).
- `GET /api/coverage/dashboard?persona=&dimension=&radius_km=` — 페르소나 필터, 4 차원 원본 수치 동시 반환(클라이언트 토글 재호출 불필요), haversine 기반 거점 도달권 판정.
- `/churn` · `/tier-up` 페이지에 *지도 탭* 추가. 백엔드 `GET /api/churn/map?persona=` (시도별 평균 이탈 위험 + at-risk 수) · `GET /api/tier-up/map?persona=` (시도별 Silver/Gold/후보 밀도 + Gold 임계 갭) 신설.

### 추가 — 페르소나 spine ↔ narrative 브릿지
- 5-spine `Persona` 노드 (`per_pregnant`, `per_kid_4yo_mom`, `per_camper`, `per_sensitive_skin`, `per_gluten_allergy`) — `is_spine=true` 속성으로 `load_membership` 시작점에서 MERGE. 기존 40 narrative `psn_*` 노드와 비파괴 공존 → 총 Persona 수 45.
- `(narrative:Persona)-[:DERIVED_FROM]->(spine:Persona)` keyword 기반 브릿지 엣지 (9 narrative에서 10 엣지, 다중 매핑 지원 — 예: `psn_002` "워킹맘 (4세 글루텐알레르기)" 가 `per_kid_4yo_mom` + `per_gluten_allergy` 둘 다 연결).
- `GET /api/personas?segment_eligible=true` — spine + bridged narrative 만 반환 (~14개). 항목마다 `is_spine`, `is_bridged`, `bridge_targets` 노출하여 클라이언트가 그룹/배지 표시 가능.

### 변경
- 시나리오 카드 11 → 12개. 사이드바·홈페이지·가이드투어 자동 동기화.
- PersonaSwitch 위젯이 `listPersonas` 호출에 `segment_eligible: true` 부여, 항목을 **5-spine 페르소나** (상단, SPINE 배지) + **Narrative (bridged)** 두 그룹으로 표시. 표시되는 어떤 페르소나를 골라도 지도 엔드포인트가 0명을 반환하지 않음을 보장.
- Coverage / churn /map / tier-up /map 라우터가 `MATCH (m:Member)-[:LIVES_IN]->(r:Region)` 트래버설 (LIVES_IN 엣지를 region 권위로) + OR 패턴 `(m)→spine OR (m)→spine←DERIVED_FROM←narrative` 적용.
- 사이드바 버전 `v0.2.0` → `v0.5.0`. `web/package.json` version 필드도 동기.
- `docs/membership.md` §8 "회원 위치 없음" 한계 해소 반영, 변경 이력에 Phase 2A-G 추가.

### 수정
- `/coverage`, `/churn /map`, `/tier-up /map` 가 `?persona=` 부여 시 **500 MalformedQueryException** 반환하던 버그 — Neptune openCypher 엔진이 `EXISTS { MATCH ... }` subquery form을 거부. 보편적 호환성을 갖는 pattern-expression form `(m)-[:R]->(...)` 으로 전환.
- 모든 페르소나 필터 쿼리가 **0명** 반환하던 버그 — 합성 데이터는 `per_*` ID를 쓰지만 `personas.ndjson`에는 narrative `psn_*` 40개만 들어있어 로더의 `MATCH (per:Persona {persona_id: $pid})` 가 silently 0 엣지 생성. 위 spine MERGE + DERIVED_FROM 브릿지로 해소.
- "**선택하면 회원수 0**" UX 실패 — narrative 페르소나 선택 시 Coverage/Churn map/Tier-up map 빈 응답. narrative가 DERIVED_FROM 으로 spine에 도달, 매핑 안되는 narrative는 `segment_eligible=true` 로 picker에서 숨김.

## [0.2.0] — 2026-05-01

24시간에 22 커밋 — Phase 1 (그래프 밀도 토글) + Phase 2 (멤버십·마케팅 레이어, 시나리오 I/J/K) +
배포 후 보정(Sidebar wiring, Bedrock toolResult 형식 fix, AgentCore Memory wire format,
Cognito redirect_uri, ECR push 파이프라인). Sidebar 버전 `v0.1` → `v0.2.0`.

### Added — 시나리오 I·J·K (멤버십 / 마케팅)
- 시나리오 I (`/churn` + `/api/churn/*`): RFM 기반 이탈 위험 진단 — 등급별/페르소나별 분포, top-30 위험 회원 리스트, 회원 드릴다운(거래·접점·winback 추천), Cytoscape 1-hop
- 시나리오 J (`/acquisition` + `/api/acquisition/dashboard`): 캠페인·채널 ROI 롤업 (single-touch attribution) + 페르소나×채널 응답률 히트맵
- 시나리오 K (`/tier-up` + `/api/tier-up/dashboard`): Silver→Gold 코호트 lift (Laplace 평활) + 업그레이드 후보 (Silver, LTV ≥1.5M)
- 사이드바 3개 항목 (배지 I/J/K), GuidedTour 3 스텝, api-client 3 함수

### Added — 멤버십 데이터 레이어
- 5개 신규 노드 (`Member`, `MembershipTier`, `Campaign`, `Transaction`, `Touchpoint`) + 8개 신규 엣지 (`BELONGS_TO`, `MATCHES_PERSONA`, `PREFERS_CHANNEL`, `MADE`, `OF_PRODUCT`, `HAS_TOUCHPOINT`, `FROM_CAMPAIGN`, `TARGETS`)
- `data/synthetic/membership.py` — 1,000명 회원 + 20 캠페인 + ~7.8k 거래 + ~10k 접점 결정론적 생성 (SHA1 PRNG). 첫 3명은 데모용 실명 fixture (홍길동/김영희/최우형)
- RFM 기반 `churn_risk` + 페르소나-등급 상관 (임산부·아이맘 → 고LTV, 캠퍼 → 시즌 Silver)
- `data/load.py:load_neptune` 의존 순서로 wiring; `_TYPE_REGISTRY` (objects), `_CLASSES`+`_RELATIONS` (ontology), `TYPE_META` (object explorer), 사이드바 객체 탐색 섹션 모두 5종 추가 반영

### Added — 에이전트 도구
- 3개 물류 도구 (`api/services/agent.py:TOOL_SPECS`): `nearest_warehouses` (region_name → lat/lng + haversine + cold-only), `shortest_path` (한국어 이름 → wh_id + Route BFS, 최대 4 hop), `inventory_lookup` (wh_id 또는 sku_id)
- 17개 한국 주요 도시 좌표 매핑 (Neptune round-trip 절약)
- `agent.recent_traces()` 200-entry ring buffer + `_push_trace` (도구 dispatch 시점) — `/api/ops/trace` 500 fix

### Added — UX / 스트리밍
- CytoscapeView 밀도 토글 (조밀/보통/넓게) — cose `nodeRepulsion` / `idealEdgeLength` / `gravity`
- 검색·인사이트·대화형 라이브 phase strip — SSE phase 이벤트가 도착하는 대로 색상 chip 누적 (검색: BM25/KNN/RRF/rerank, 인사이트: Neptune/Sonnet 4.6, 대화형: guardrail/memory/bedrock/tool:*/guardrail-out)
- 대화형 빈 상태에 10개 페르소나 태그 추천 풍선말 — 클릭 즉시 전송, 페르소나별 색상 (임산부/4세 아이/캠퍼/민감성/글루텐/계절성/멤버십)
- 대화 기록 export — MD 다운로드 (Blob, 메시지별 role 헤더 + 본문 + 도구호출 부록) + PDF 다운로드 (jsPDF + html2canvas, 760px 오프스크린 → A4 페이지네이션, lazy import ~250KB)
- react-markdown v10 + remark-gfm 렌더링 (chat / insights), 공유 `MarkdownView` 컴포넌트, `.chat-markdown` 스타일 globals.css에 통합
- 홈 대시보드 11개 시나리오 카드 (A–K, 색상 구분) + Knowledge Graph 객체 5 group 서브그리드 (상거래·라이프스타일·리뷰·물류·**멤버십**)

### Added — API 엔드포인트
- `GET /api/auth/login` (Cognito Hosted UI redirect helper) + `GET /api/auth/whoami` (id_token decode → claims)
- `POST /api/search/stream` + `POST /api/insights/stream` SSE — `phase`/`delta`/`result` 이벤트. insights는 Sonnet 4.6 `converse_stream` 직접 호출 (3-section MD 답변)
- working tree에만 있던 6개 라우터를 `api/main.py`에 등록: `logistics, ops, persona_match, price, safety, substitute`

### Changed — Layout / wiring
- `516c38e`(4/28) 시점 대시보드 레이아웃 복원 — `tailwind.config.ts`의 `ink-50..950` + `accent-100..700` 팔레트 복원 + `app/layout.tsx`에 Sidebar wiring (좌 rail + 메인 + 우상단 PersonaSwitch/GuidedTour)
- 객체 탐색 collapsible inspector + breadcrumb — 속성 접기 시 그래프 폭 ~95%, 라벨별 sampling Cypher (각 15)로 Channel 1-hop이 Member-only가 아닌 Member+Product+Warehouse 모두 표시
- 객체 탐색 그래프 노드 탭 → cross-type detail 로드 (`LABEL_TO_SLUG` 매핑)
- 거래/접점 친화 라벨 — `2026-04-15 · 35,000원 · sku_xxx`로 표시 (opaque ID 대체)
- 대화형 입력 form 상단 배치 (검색·인사이트와 동일 패턴)

### Fixed
- Bedrock Converse `toolResult.content[].json` — `semantic_search` / `kb_lookup`이 list를 반환하면 ValidationException 발생 → `{items, count}`로 wrap (도구 호출만 보이고 결과 미출력 issue의 진짜 원인)
- AgentCore Memory `create_event` wire format — `actorId` (snake_case 아닌), `eventTimestamp` (UTC datetime), `payload` list of conversational blocks. 실패는 swallow하여 chat 생존
- `/api/auth/callback` Host 헤더 의존성 제거 — CloudFront `Managed-AllViewerExceptHostHeader`가 Host strip → `PUBLIC_DOMAIN` env로 redirect_uri 직접 구성
- `/api/objects/*`, `/api/ontology/*` 라우터 `main.py` 등록 누락 fix (production 404)
- API 컨테이너에 `COPY ontology /app/ontology` 추가 — `/api/ontology/standards` 빈 배열 / validation 0% 커버리지 fix
- `data/load.py` `Optional` 타입 import 누락 (PEP 563 덕에 런타임 무해, 정적 검사 fix)
- `web/lib/api-client.ts` `personaMatch`/`substitute`/`priceCompare` positional args 시그니처 매칭 + 본문 빌드
- next.config.mjs에 `typescript.ignoreBuildErrors` + `eslint.ignoreDuringBuilds` (PoC 빌드 unblock)
- 루트 layout SSG prerender — `<PersonaProvider>`로 children 감싸기

## [0.1.0] — 2026-04-28

### Added — CI / 테스트 하니스
- `.github/workflows/ci.yml` 4-job CI 파이프라인 추가 — `python-ast` (compileall), `tsc-check` 매트릭스 [web, infra-cdk], `cdk-synth` + jest 스냅샷, `pytest`. push/PR 트리거 + concurrency cancel-in-progress
- `tests/` pytest 스위트 추가 — 28 tests / <1초: 16 라우터 import smoke (`tests/test_smoke.py`) + 5 Pydantic 모델 검증 + 2 health + 5 `/api/search` 통합 (httpx.AsyncClient + boto3 import-site mock)
- `tests/conftest.py` — collection 시점에 18개 더미 env 설정 + `DEMO_PUBLIC_MODE=true` + `REQUIRE_ORIGIN_AUTH=false`로 ASGI-direct 테스트 가능
- `infra-cdk/test/stacks.test.ts` — 6 CDK 스택 Jest 스냅샷 테스트 (`Template.fromStack().toJSON()`), 결정적 테스트 컨텍스트(account `000000000000`); 7727줄 자동생성 스냅샷
- `requirements-dev.txt` — pytest, pytest-asyncio, httpx (CI 전용, 프로덕션 Docker 이미지에는 미설치)
- `tests/CLAUDE.md` — 테스트 레이아웃, conftest 계층, ASGI fixture, mock-at-import-site 규칙, 스냅샷 업데이트 흐름 문서화
- `docs/decisions/` ADR 4건 추가 — 0001 AgentCore Memory CDK AwsCustomResource, 0002 CloudTrail L1 CfnTrail + manual bucket policy, 0003 Lambda@Edge stable-ID hardcode, 0004 Cognito UserPoolClient CDK-only
- `.claude/settings.json` (프로젝트 공유) — `PreToolUse` + `PostToolUse` + `Stop` 후크 등록 + 60-entry `permissions.deny` (MCP namespace bypass, CloudTrail audit-blinding, AWS IAM 권한 상승 triad 차단)
- `.claude/hooks/scrub-secrets.sh` — Pre/PostToolUse에서 AKIA/ASIA, JWT, PEM private key, Slack token, GitHub PAT 차단
- `.claude/hooks/changelog-reminder.sh` — Stop 시점에 구조적 파일 변경(api/routers, infra-cdk/lib 등)이 있는데 CHANGELOG가 안 바뀌면 알림
- `.claude/skills/{wow-query-eval,cypher-conventions}.md` — 프로젝트 특화 skill 2종
- `.claude/agents/{code-reviewer,security-auditor}.md` — `model: sonnet` 고정, severity taxonomy + finding shape + termination phrase 명시한 `## Output format` 섹션
- 5개 모듈 `CLAUDE.md` git-tracked (api/, web/, data/, infra-cdk/, ontology/) + 루트 `CLAUDE.md`
- `.harness-eval/` 점수 history — 4회 평가 기록 (6.0/C → 5.5/D → 6.9/C → 7.9/B); README 배지 자동 갱신
- 시나리오 H 물류 네트워크 추가 — 한국 시도 choropleth 지도(`react-simple-maps` + KOSTAT 17 시도 GeoJSON), 30 거점, 76 lane, KPI 스트립, 인라인 LLM 챗 패널
- Inventory를 first-class 지식그래프 노드로 추가 — 940 row, cold-chain 인지 결정적 합성, `Inventory→Warehouse [HELD_AT]` + `Inventory→Product [OF_SKU]` 엣지
- 물류 온톨로지 클래스 추가 — Region (51), Warehouse (30), Carrier (7), Route (76), Shipment (500), Event (12) + 엣지 `LOCATED_IN`, `OPERATES`, `FULFILLED_BY`, `FROM`/`TO`, `CARRIED_BY`, `VIA`, `CONTAINS`, `AFFECTS_REGION`, `AFFECTS_CATEGORY`
- 채팅 에이전트에 물류 LLM 도구 3종 추가 — `inventory_lookup`, `nearest_warehouses` (haversine k-NN), `shortest_path` (Route 엣지 위 BFS)
- 물류 엔드포인트 추가 — `/api/logistics/{network,warehouse/...,events,status,inventory/wh/...,inventory/sku/...,nearest,shortest-path}`
- `/logistics` 우측 패널을 탭(거점·운송사 / 물류 도우미)으로 재구성 — LLM 챗을 floating에서 always-visible 인라인으로 전환
- 시나리오 G 가격·가용성 비교 추가 — 4채널 매트릭스 + 페르소나-채널 친화도 가중치
- 지식그래프 사이드바에 Manufacturer, Review 객체 탐색 타입 추가
- `/validation` 매핑 검증 리포트 추가 — INCI/FoodOn/GS1+KFDA/Loader 커버리지
- `/ops/trace` 운영 트레이스 뷰어 추가 — in-process 도구 호출 ring buffer 200건
- 우상단 PersonaSwitch 전역 위젯 추가 — 활성 페르소나를 search/chat API에 자동 주입
- 첫 방문 시 자동 노출되는 5분 가이드 투어 오버레이 추가 — 시나리오 A–G 안내
- `/api/search`의 SSE 스트리밍 변형 추가 — phase 타임라인(guardrail, embed, KNN, BM25, RRF, rerank, subgraph)
- `/api/insights`의 SSE 스트리밍 변형 추가 — Sonnet 토큰 delta + phase 타임라인(Neptune-agg, LLM, Code Interpreter, drilldown)
- 한국 식품 온톨로지 보충 — `ontology/mappings/foodon-to-korean.json` 219건 한글 별칭
- 결정적 `_assign_channels()` 합성으로 Channel→Product `AVAILABLE_IN` 엣지 적재 (CU/이마트/올리브영/마컬)
- `/api/auth/whoami`, `/api/auth/login`, `/api/auth/logout` 엔드포인트 + 사이드바 하단 로그인/아웃 위젯 추가
- 커스텀 도메인 `retail-ontology.whchoi.net` 연결 — ACM `*.whchoi.net` 인증서, Cognito 콜백 등록

### Changed
- `.claude/agents/*.yml` → `.md` 변환 + YAML frontmatter, `model: sonnet` 고정, severity taxonomy + finding shape + termination phrase 포함된 `## Output format` 섹션 추가
- `.claude/settings.local.json` allow list 244 → 75 (-69%) 컴팩션 — `tee /tmp/*-deploy*.log` 22개 → `Bash(tee /tmp/*)`, awk 1회성 9개 → `Bash(awk *)`, dig 7개 → `Bash(dig *)`, 하드코딩 ALB/CloudFront curl 17개 → `Bash(curl -*)`, `cdk deploy --require-approval never` 12개 (이미 deny 처리)
- `scripts/eval_wow_queries.py` 임계값 게이트 강화 — <85% pass-rate에서 `sys.exit(1)` (이전: <70%에서 warn-only); `.claude/commands/test-all.md`의 임계값과 일치
- 대화형 에이전트 UI 구조를 의미 검색·MD 인사이트와 통일 — 입력 폼을 최상단으로, 샘플 풍선을 폼 하단으로 이동
- 가격 비교 결과 카드 음영 계층 정리 (페이지 → 카드 → 서브카드)
- 온톨로지 관계 `Channel → Product STOCKS`를 로더 의미에 맞게 `Product → Channel AVAILABLE_IN`로 변경

### Fixed
- `neptune.open_cypher`에 `parameters`를 positional로 넘겨 발생한 priceCompare 500 오류 수정
- `insights/stream` f-string 표현식 내부 escaped 따옴표 SyntaxError 수정
- INCI 검증 false-negative 수정 — CSV `inci_name`을 slug 변환해 Neptune `inci:<slug>` ID와 동일 형식으로 비교
- GS1/KFDA 검증을 식품 도메인 카테고리만 검사하도록 필터 추가 (뷰티 brick은 식품 CSV 범위 외)
- `/ops/cost`의 `boto_session.client(...)` 호출을 `boto_session().client(...)`로 수정
- `docs/architecture.md` 124 라인 dead ADR link 수정 (존재하지 않는 `0001-single-image-two-roles.md` 참조 제거); 실제 4개 ADR 교차 링크 추가
- `docs/api-reference.md` `whoami`/`logout` 중복 블록 제거 (병합 잔재)

### Removed
- 운영 사이드바에서 비용 모니터 제거 (endpoint는 유지하되 노출하지 않음)

## [0.1.0] - 2026-04-27

### Added
- 실제 Lambda@Edge 쿠키 인증 및 Cognito 콜백 핸들러 추가
- `/ops/eval`에 30개 wow 쿼리 평가 하네스와 pass-rate 스코어보드 추가
- CloudTrail 관리 이벤트 로깅과 ALB 액세스 로그 추가
- Default-Services-Monitor에 Cost Anomaly 구독 추가
- 데모 계정 프로비저닝 스크립트와 함께 Cognito 사용자 풀 추가
- 하이브리드 검색(BM25 + KNN + Reranker)을 갖춘 Bedrock Knowledge Base 추가
- AgentCore Memory short-term, long-term 네임스페이스 추가
- 한글 폰트 matplotlib 차트를 위한 Code Interpreter 샌드박스 추가
- 시나리오 A–F(의미 검색, 채팅, 인사이트, 페르소나 매칭, 안전성, 대체재) 베이스라인 7종 + 지식그래프 객체 탐색기 추가

### Changed
- **BREAKING:** 모든 Bedrock Converse 호출의 채팅·인사이트 모델을 Haiku Lite에서 Sonnet 4.6으로 변경
- Secrets Manager 호출량 절감을 위해 origin auth secret을 5분 TTL로 캐시

### Fixed
- 리랭커 cross-region inference profile 비가용 시 fallback 처리 수정
- AOSS bulk indexing이 문서별 오류를 표면화하고 자동 생성 `_id`를 사용하도록 수정
- Edge Stack CFN dynamic reference 및 Neptune `_flatten_props` 스칼라 강제 변환 수정
- Neptune 클라이언트를 수동 SigV4 서명 대신 `boto3.neptunedata`로 변경
- JWKS 조회에 TTL 캐시 적용 및 origin 토큰을 상수 시간 비교로 수정
- Neptune IAM 액션을 `neptune-db:*` 와일드카드로 수정 (개별 액션은 403 반환)
- CloudTrail 구독을 management 이벤트 타입에 한정하도록 수정

### Security
- Origin 공유 비밀을 Secrets Manager로 회전하고 Cognito JWT는 RS256으로 검증
- AuthMiddleware를 FastAPI 메인 엔트리에 연결
- CORS 허용 목록 강화 및 비밀번호 회전 정책 문서화
- AgentCore Memory IAM을 최소 권한으로 좁히고 데모 계정 Cognito 비밀번호를 8자로 완화
- OpenSearch에서 계정 root 정책 제거 및 portable cost monitor 조회로 변경

[Unreleased]: https://github.com/whchoi98/ontology-retail/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/whchoi98/ontology-retail/releases/tag/v0.1.0
