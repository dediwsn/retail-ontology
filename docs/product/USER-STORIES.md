# User Stories — Ontology Retail Intelligence Platform

Companion to [PRD.md](PRD.md). Stories are grouped by role, written in the standard
*As a … I want … so that …* form, and each carries **acceptance criteria** in Given/When/Then form
plus the **capability** that satisfies it.

**Legend** — `A`–`M` are the thirteen scenarios; `OBJ` = Object Explorer; `ONT` = Ontology Meta;
`OPS` = Operations Console; `PLT` = Platform-wide.

**Status key** — ✅ shipped and demonstrable · 🔧 shipped, needs customer data · 🗓 roadmap.

---

## Epic 1 — Find the right product in Korean (Scenario A, F, G)

### US-1.1 — Intent-aware Korean search ✅ `A`
> **As a** shopper on the retail site,
> **I want** to type "임산부가 써도 되는 저자극 선크림" in plain Korean
> **so that** I get products that are actually suitable, not products that merely contain the words.

**Acceptance criteria**
- **Given** a free-form Korean query, **when** I submit it, **then** results are produced by fusing
  Nori-analyzed BM25 with Cohere `embed-v4` vector search via reciprocal-rank fusion, and reranked by
  `cohere.rerank-v3`.
- **Given** the reranker is unavailable, **when** I search, **then** results still return in RRF order
  rather than erroring.
- **Given** a result, **when** I inspect it, **then** a 1-hop subgraph shows the ingredient, concern,
  trend or brand that caused the match.
- **Given** a slow query, **when** streaming is used (`/api/search/stream`), **then** partial results
  render progressively.

### US-1.2 — Explain why a product matched ✅ `A` `OBJ`
> **As a** merchandiser reviewing search quality,
> **I want** to see the graph path behind each result
> **so that** I can tell a relevance bug from a data-mapping bug.

**Acceptance criteria**
- **Given** any search result, **when** I open its subgraph, **then** every edge is labelled with its
  relationship type and every node is clickable through to the Object Explorer.
- **Given** I click a node, **when** the explorer opens, **then** it shows that instance's full
  property set and 1-hop neighbourhood.

### US-1.3 — Find a substitute when the first choice fails ✅ `F`
> **As a** shopper whose preferred item is out of stock or too expensive,
> **I want** alternatives in the same category from other brands
> **so that** I complete the purchase instead of abandoning the basket.

**Acceptance criteria**
- **Given** a SKU, **when** I request substitutes, **then** I receive 5–8 candidates from the same
  category and a different brand.
- **Given** each candidate, **when** it is displayed, **then** it shows the ingredient/concern overlap
  score and the price delta against the original.

### US-1.4 — Compare price and stock across channels ✅ `G`
> **As a** price-sensitive shopper (or a pricing manager),
> **I want** one view of price, discount and stock across CU, 이마트, 올리브영 and 마켓컬리
> **so that** I buy from — or price against — the right channel.

**Acceptance criteria**
- **Given** a natural-language need, **when** I submit it, **then** the system recommends a SKU and
  renders a four-channel matrix of price, discount and stock.
- **Given** an active persona, **when** the matrix renders, **then** channel ordering reflects that
  persona's channel affinity.

---

## Epic 2 — Trust what I'm buying (Scenario E)

### US-2.1 — Pregnancy-safe filtering ✅ `E`
> **As a** pregnant shopper,
> **I want** products screened against a pregnancy safety profile
> **so that** I never have to read an INCI list myself.

**Acceptance criteria**
- **Given** the pregnancy profile is active, **when** a product contains an ingredient on the
  avoid-list, **then** the product is flagged and **the specific ingredient is named**.
- **Given** a flagged product, **when** I inspect the reason, **then** the traversal path
  (Product → HAS_INGREDIENT → Ingredient ← AVOIDS_INGREDIENT ← Profile) is shown.
- **Given** the same input twice, **when** evaluated, **then** the verdict is identical — the check is
  deterministic graph traversal, not a model judgement.

### US-2.2 — Pediatric, allergen and lifestyle profiles ✅ `E`
> **As a** parent, an allergy sufferer, or a vegan shopper,
> **I want** the same screening for my own profile
> **so that** one mechanism covers every restriction I have.

**Acceptance criteria**
- **Given** the profile list at `GET /api/safety/profiles`, **when** I select pediatric, gluten-free,
  vegan or sensitive-skin, **then** screening applies the corresponding avoid-list.
- **Given** a grocery SKU, **when** screened, **then** FoodOn/KFDA mappings are used; **given** a beauty
  SKU, **then** INCI mappings are used.

### US-2.3 — Compliance sign-off with an audit trail 🔧 `E` `OPS`
> **As a** 품질/규제 담당,
> **I want** an auditable record of every safety decision and every guardrail intervention
> **so that** I can defend the assortment to a regulator.

**Acceptance criteria**
- **Given** guardrails intervene on any input or output, **when** I open the Operations console,
  **then** the intervention is listed with its timestamp and reason.
- **Given** a period of interest, **when** I query `GET /api/ops/guardrail`, **then** I receive the
  interventions for that window.
- 🗓 **Given** production compliance requirements, **then** Bedrock model invocations are additionally
  captured as CloudTrail data events *(production-readiness item 5)*.

---

## Epic 3 — Ask the data anything (Scenario B, C)

### US-3.1 — Multi-turn conversation with memory ✅ `B`
> **As a** returning user,
> **I want** the assistant to remember my earlier turns and my long-term preferences
> **so that** I don't restate my constraints every session.

**Acceptance criteria**
- **Given** a prior turn established a constraint, **when** I ask a follow-up, **then** the constraint
  is honoured without restating it.
- **Given** a new session by the same user, **when** I ask a related question, **then** long-term facts
  are recalled from the AgentCore Memory user namespace (7-day TTL).
- **Given** any session, **when** I open `GET /api/ops/memory`, **then** I can inspect exactly what was
  stored.

### US-3.2 — See the agent's work ✅ `B` `OPS`
> **As a** technical evaluator,
> **I want** to watch every tool call the agent makes, live
> **so that** I can verify the answer is grounded rather than generated.

**Acceptance criteria**
- **Given** a chat turn, **when** the agent invokes a tool, **then** a `log` SSE event streams the tool
  name and arguments to a visible panel.
- **Given** the seven registered tools (`memory_recall`, `neptune_subgraph`, `semantic_search`,
  `kb_lookup`, `inventory_lookup`, `nearest_warehouses`, `shortest_path`), **when** any is called,
  **then** it appears in the trace ring buffer readable at `GET /api/ops/trace`.
- **Given** a streaming response, **when** it renders, **then** every event conforms to the shared
  `{type: phase|delta|log|final|result, data: {…}}` vocabulary.

### US-3.3 — Self-serve trend analysis with real charts ✅ `C`
> **As an** MD preparing a weekly category review,
> **I want** a Korean summary plus an actual chart, generated on demand
> **so that** I stop filing BI tickets a week ahead of every meeting.

**Acceptance criteria**
- **Given** a trend question, **when** I submit it, **then** Neptune aggregation runs first and the
  Sonnet 4.6 summary streams token-by-token over the aggregated result.
- **Given** the summary completes, **when** the chart renders, **then** it is a PNG produced by
  matplotlib executing inside the AgentCore Code Interpreter microVM, with Korean glyphs rendered via
  the bundled NanumGothic font.
- **Given** any figure in the summary, **when** I drill down, **then** a 1-hop subgraph shows the
  underlying entities.

### US-3.4 — Ask logistics questions in the map itself ✅ `H` `B`
> **As a** supply-chain planner looking at the network map,
> **I want** to ask "이 SKU 재고가 가장 많은 센터는?" without leaving the page
> **so that** exploration and question-asking are the same activity.

**Acceptance criteria**
- **Given** the `/logistics` page, **when** I use the inline LLM panel, **then** it can call
  `inventory_lookup`, `nearest_warehouses` (haversine k-NN) and `shortest_path` (BFS over lanes).
- **Given** a nearest-warehouse question, **when** answered, **then** the named warehouses are
  highlighted on the map.

---

## Epic 4 — Know my members (Scenario D, I, J, K)

### US-4.1 — Persona-driven recommendation ✅ `D`
> **As a** personalisation owner,
> **I want** SKU recommendations derived from a persona's concerns and ingredient preferences
> **so that** recommendations are explainable to the merchandising team.

**Acceptance criteria**
- **Given** one of forty narrative personas, **when** I request a match, **then** the walk traverses
  `HAS_CONCERN` → preferred/avoided ingredients → products and returns weighted SKUs.
- **Given** a narrative persona, **when** any downstream scenario needs members, **then** the
  `DERIVED_FROM` bridge resolves it to a spine persona so member-level data is still available.

### US-4.2 — Diagnose churn risk before it happens ✅ `I`
> **As a** CRM manager,
> **I want** every member scored for churn risk from RFM
> **so that** I intervene on a ranked list instead of a hunch.

**Acceptance criteria**
- **Given** the churn dashboard, **when** it loads, **then** it shows risk distribution broken down by
  membership tier and by persona.
- **Given** the Top-30 at-risk list, **when** I open a member, **then** I see their recency, frequency,
  monetary values and a 1-hop graph of their purchases and touchpoints.
- **Given** an at-risk member, **when** I request a winback action, **then** the recommendation is
  persona-aware.
- **Given** the map tab, **when** it renders, **then** the 17 시도 are shaded by average churn risk.

### US-4.3 — Allocate acquisition budget by evidence ✅ `J`
> **As a** performance-marketing lead,
> **I want** ROI per campaign and per channel, plus a persona × channel response heatmap
> **so that** I stop funding channels that only look busy.

**Acceptance criteria**
- **Given** the acquisition dashboard, **when** it loads, **then** ROI is computed as campaign cost
  divided by LTV attributed from **responded** touchpoints only.
- **Given** the heatmap, **when** I read a row, **then** the best-performing channel for that persona
  archetype is identifiable at a glance.

### US-4.4 — Find the members most likely to upgrade ✅ `K`
> **As a** loyalty-programme owner,
> **I want** the products and categories that statistically lift Silver members to Gold, and a ranked
> candidate list
> **so that** upgrade offers are targeted rather than blanket.

**Acceptance criteria**
- **Given** the tier-up dashboard, **when** lift is computed, **then** it is per-capita Gold rate ÷
  Silver rate with Laplace smoothing, so small-N categories do not dominate.
- **Given** the candidate list, **when** it renders, **then** it contains Silver members with LTV ≥
  ₩1.5M sorted by gap-to-Gold.
- **Given** the map tab, **when** it renders, **then** 시도 are shaded by candidate density.

---

## Epic 5 — Grow share of wallet (Scenario M) — the differentiator

### US-5.1 — See what a member spends *outside* our stores ✅ `M`
> **As a** CRM strategist,
> **I want** external consumption panel spend joined to our own transactions
> **so that** I know our wallet share per member per category, not just our revenue.

**Acceptance criteria**
- **Given** a member and an industry category, **when** wallet share is computed, **then** it equals
  `our_internal ÷ (our_internal + external)`, where the internal side is resolved through the
  `OVERLAPS_WITH` bridge from industry category to GS1 brick category.
- **Given** two quarters of panel data (Q4 2025 and Q1 2026), **when** trends are computed, **then**
  quarter-over-quarter growth ratios are available per member.
- **Given** an industry with no overlapping internal category, **when** share is computed, **then** it
  correctly reports 0% — an explicit blind spot, not a missing value.

### US-5.2 — Build five different VIP lists from one dataset ✅ `M`
> **As a** VIP programme owner,
> **I want** five simultaneous, independently tunable VIP definitions
> **so that** offence, defence and growth strategies each get the right list.

**Acceptance criteria**
- **Given** the Opportunity tab, **when** I set a share ceiling and a total-spend floor, **then** I get
  members with low our-share and high category spend, ranked by untapped ₩ upside.
- **Given** the Loyal tab, **when** I set a share floor (default 0.5) and total floor (default ₩300k),
  **then** I get members where we already hold majority share — the defensive list.
- **Given** the Whale tab, **when** I set an LTV floor (default ₩5M), **then** I get internal `tier=VIP`
  members with monetary, frequency, recency and churn risk for retention prioritisation.
- **Given** the Cross-category tab, **when** it runs, **then** it returns members buying exactly one
  internal category whose external spend in a **non-overlapping** industry exceeds the floor, and it
  names the industry to extend into.
- **Given** the Trajectory tab, **when** I set a growth floor (default 1.2×), **then** I get non-VIP
  members whose spend is rising fastest — the "future VIPs".
- **Given** any tab, **when** the active persona changes, **then** the candidate list re-slices to that
  persona.
- **Given** any slider, **when** I move it, **then** the candidate count and list update — thresholds
  are the operator's to tune, not hard-coded.

### US-5.3 — Export a target segment 🗓 `M`
> **As a** campaign manager,
> **I want** to push a VIP list into the campaign tool
> **so that** analysis becomes a campaign without a manual CSV round-trip.

**Acceptance criteria** *(roadmap — write-back connectors, PRD §14)*
- **Given** a candidate list, **when** I export, **then** I receive a segment in the campaign tool's
  expected schema.
- **Given** an export, **when** it completes, **then** the segment definition (filters and thresholds)
  is recorded alongside it for reproducibility.

---

## Epic 6 — Serve every member (Scenario H, L)

### US-6.1 — See the fulfilment network on a map ✅ `H`
> **As a** logistics manager,
> **I want** warehouses, lanes, inventory and disruption events on one Korean map with a KPI strip
> **so that** network state is a glance, not a report.

**Acceptance criteria**
- **Given** the network view, **when** it loads, **then** 30 warehouses, 76 lanes and 940 inventory
  rows render over the KOSTAT 17-시도 GeoJSON.
- **Given** the KPI strip, **when** it renders, **then** it shows OTD rate, active shipments, transit
  time, exceptions and active events.
- **Given** an active disruption event, **when** it affects a region or category, **then** the affected
  geography is visibly marked.

### US-6.2 — Quantify the coverage gap for a persona ✅ `L`
> **As a** network-planning lead building an expansion business case,
> **I want** one number — the share of a persona's members with no fulfilment node within N km
> **so that** the case for a new site is a single defensible KPI.

**Acceptance criteria**
- **Given** a persona and a radius, **when** the dashboard loads, **then** the headline KPI reads
  "내 페르소나 회원 중 N km 안에 거점이 없는 비율".
- **Given** the radius slider, **when** I move it, **then** the KPI and the choropleth update together.
- **Given** the dimension toggle, **when** I switch it, **then** the map re-shades by member count,
  average churn risk, average LTV, or uncovered share.
- **Given** the map, **when** it renders, **then** warehouse markers overlay the member choropleth so
  the gap is visually obvious.

### US-6.3 — Cross-read membership against logistics ✅ `L` `I` `K`
> **As a** COO,
> **I want** the same geography shared by churn, tier-up and coverage views
> **so that** "our worst-served region" and "our highest-churn region" are comparable on sight.

**Acceptance criteria**
- **Given** scenarios H, I, K and L, **when** each renders its map, **then** all four use the same
  17-시도 `Region` nodes and the same projection.
- **Given** a region, **when** I compare views, **then** the same region identifier holds across
  membership geography (`LIVES_IN`) and logistics geography (`LOCATED_IN`).

---

## Epic 7 — Understand and govern the ontology (OBJ, ONT)

### US-7.1 — Browse every entity type ✅ `OBJ`
> **As a** data steward,
> **I want** a browsable view of all 21 registered node types
> **so that** I can inspect what the graph actually contains without writing Cypher.

**Acceptance criteria**
- **Given** the Object Explorer, **when** I pick a type, **then** instances are listed ranked by graph
  fan-out (e.g. products by ingredient count, brands by product count).
- **Given** an instance, **when** I open it, **then** I see its full property set and 1-hop neighbours.
- **Given** a newly added node type, **when** it is registered, **then** it appears in all six mandated
  locations (API registry, explorer metadata, sidebar, ontology classes/relations, home page chips,
  and the data schema) — enforced by a documented auto-sync rule.

### US-7.2 — See the ontology as a diagram ✅ `ONT`
> **As a** solution architect evaluating the model,
> **I want** an ER diagram of classes and relationships
> **so that** I can judge whether my own domain fits this shape.

**Acceptance criteria**
- **Given** `/schema`, **when** it loads, **then** a Cytoscape diagram renders every class and relation
  from `GET /api/ontology/schema`.

### US-7.3 — Verify standards coverage ✅ `ONT`
> **As a** compliance or master-data owner,
> **I want** to browse the INCI / FoodOn / GS1↔KFDA mapping files and their coverage
> **so that** I know exactly how much of the assortment is standards-aligned.

**Acceptance criteria**
- **Given** `/standards`, **when** I select a mapping file, **then** its rows are browsable in-app.
- **Given** `/validation`, **when** it loads, **then** coverage is reported per standard (INCI, FoodOn,
  GS1+KFDA, loader).

---

## Epic 8 — Operate the platform (OPS, PLT)

### US-8.1 — Verify the data actually loaded ✅ `OPS`
> **As an** operator after a data reload,
> **I want** per-entity ingest counts
> **so that** I catch a partial load before a stakeholder does.

**Acceptance criteria**
- **Given** `GET /api/ops/ingest`, **when** called after a load, **then** counts per node type are
  returned and comparable against the expected reference volumes.
- **Given** a reload, **when** it uses the same seed, **then** the counts are identical — determinism is
  verifiable, not assumed.

### US-8.2 — Prove answer quality with a score ✅ `OPS` `PLT`
> **As a** platform owner,
> **I want** a scenario-level evaluation pass rate
> **so that** quality regression is caught mechanically.

**Acceptance criteria**
- **Given** the wow-query evaluation, **when** the pass rate falls below 85%, **then** the run exits
  non-zero and fails the gate.
- **Given** `GET /api/ops/eval`, **when** called, **then** the current scoreboard is returned; with
  `run=true` a fresh evaluation is executed.

### US-8.3 — Control cost ✅ `OPS`
> **As a** finance-conscious platform owner,
> **I want** a rolling cost view and anomaly alerting
> **so that** an LLM cost surprise is caught in days, not at month-end.

**Acceptance criteria**
- **Given** `GET /api/ops/cost?days=7`, **when** called, **then** recent spend is returned.
- **Given** an anomalous spend pattern, **when** AWS Cost Anomaly Detection fires, **then** an email
  notification is sent.
- **Given** the architecture, **when** reviewed, **then** there is no always-on GPU, no provisioned
  model throughput and no provisioned search cluster.

### US-8.4 — Deploy into a fresh AWS account ✅ `PLT`
> **As a** delivery engineer,
> **I want** the whole platform defined as code
> **so that** a customer environment is a deploy, not a project.

**Acceptance criteria**
- **Given** a bootstrapped account, **when** I run `npx cdk deploy --all`, **then** six stacks
  (network, data, compute, ai, edge, observability) provision the full environment.
- **Given** a data load is needed, **when** I run the one-shot ECS task with a command override,
  **then** the same API container image loads Neptune and OpenSearch — no second image, no second
  pipeline.
- **Given** an infrastructure change, **when** CI runs, **then** CDK snapshot tests surface the exact
  template diff for review.

### US-8.5 — Keep unauthenticated users out ✅ `PLT`
> **As a** security reviewer,
> **I want** authentication enforced at the edge, before any origin request
> **so that** an anonymous visitor never reaches application code.

**Acceptance criteria**
- **Given** an unauthenticated request to `/`, **when** it hits CloudFront, **then** Lambda@Edge
  returns a 302 to the Cognito Hosted UI — no partial SPA shell renders.
- **Given** the public-path whitelist, **when** audited, **then** it contains only `callback`,
  `logout`, `_next`, `favicon` and `api/health`.
- **Given** the ALB, **when** its security group is audited, **then** ingress is restricted to the
  AWS-managed CloudFront origin-facing prefix list, making direct internet access impossible.
- **Given** a CloudFront→origin request, **when** it arrives, **then** it carries a Secrets-Manager
  backed `X-Origin-Auth-Token` compared in constant time — enforced today via
  `REQUIRE_ORIGIN_AUTH=true` on the API task definition.
- **Given** a presented JWT, **when** the API verifies it, **then** verification is full RS256:
  signature against the `kid`-matched JWK from JWKS, issuer, expiry and audience.
- 🔧 **Given** production cutover, **when** `DEMO_PUBLIC_MODE=false` is set on the ECS task, **then**
  API-side JWT verification rejects all unauthenticated requests except `/healthz`
  *(production-readiness item 3)*.

### US-8.6 — Prevent query injection ✅ `PLT`
> **As a** security reviewer,
> **I want** certainty that user text never reaches the query engine as code,
> **so that** the graph cannot be manipulated through the chat box.

**Acceptance criteria**
- **Given** any Cypher execution path, **when** audited, **then** user input is passed exclusively as
  bound `parameters={…}` — never string-interpolated.
- **Given** the repository, **when** a developer attempts to commit a secret, **then** a pre-tool hook
  blocks AWS keys, JWTs, private keys and vendor tokens.

---

## Epic 9 — Sell, demo and extend (PLT)

### US-9.1 — Run a coherent 30–60 minute demo ✅ `PLT`
> **As a** solutions consultant,
> **I want** one persona selection to carry through all thirteen scenarios
> **so that** the demo tells a single story rather than thirteen disconnected ones.

**Acceptance criteria**
- **Given** the persona switch, **when** I select 캠퍼, **then** search, match, safety, churn,
  coverage and VIP all re-slice to camper-linked members and products.
- **Given** the guided tour, **when** started, **then** it steps through every scenario with
  explanatory copy.
- **Given** a reload before a meeting, **when** the seeded loader runs, **then** the demo data is
  byte-identical to the rehearsal.

### US-9.2 — Rebrand for the customer in one click ✅ `PLT`
> **As a** sales engineer walking into a customer meeting,
> **I want** the company logo swapped without a rebuild
> **so that** the demo looks like theirs, not ours.

**Acceptance criteria**
- **Given** the sidebar logo button, **when** I click it, **then** it cycles the bundled presets and
  persists the choice in `localStorage`.
- **Given** a customer SVG dropped into `web/public/logos/`, **when** registered as a preset, **then**
  it becomes selectable; setting `NEXT_PUBLIC_DEFAULT_LOGO_PRESET` makes it the default.

### US-9.3 — Show that the approach generalises ✅ `PLT`
> **As a** technical buyer sceptical that this only works for retail,
> **I want** to see the same graph technique applied to something else
> **so that** I believe it will work on my domain.

**Acceptance criteria**
- **Given** `/codegraph`, **when** it loads, **then** an AST-derived graph of the platform's own source
  (1,751 nodes / 2,217 edges / 159 communities / 151 files) is explorable.
- **Given** any community, **when** I open it, **then** a Bedrock-generated semantic label,
  description, key concepts and top files are shown — not "Community 47".
- **Given** the build, **when** audited, **then** graph extraction used **no LLM at build time**; the
  LLM was used only for offline labelling.

### US-9.4 — Add a fourteenth scenario without breaking the thirteen ✅ `PLT`
> **As an** engineer extending the platform,
> **I want** a documented checklist for every extension point
> **so that** a new scenario or node type is never half-registered.

**Acceptance criteria**
- **Given** a new scenario, **when** added, **then** the auto-sync rule enumerates every file that must
  change (sidebar, page, router, API registration, typed client, home card, API docs, changelog,
  smoke test, guided tour).
- **Given** a new node type, **when** added, **then** all six registration points are updated and a
  documented `grep` verifies it.
- **Given** any change, **when** pushed, **then** four CI jobs (Python AST, TypeScript, CDK synth +
  snapshots, pytest) gate the merge in under 13 seconds of offline runtime.

---

## Story map summary

| Epic | Stories | Shipped | Needs customer data | Roadmap |
|---|---|---|---|---|
| 1 — Find the right product | 4 | 4 | — | — |
| 2 — Trust what I'm buying | 3 | 2 | 1 | — |
| 3 — Ask the data anything | 4 | 4 | — | — |
| 4 — Know my members | 4 | 4 | — | — |
| 5 — Grow share of wallet | 3 | 2 | — | 1 |
| 6 — Serve every member | 3 | 3 | — | — |
| 7 — Understand the ontology | 3 | 3 | — | — |
| 8 — Operate the platform | 6 | 5 | 1 | — |
| 9 — Sell, demo and extend | 4 | 4 | — | — |
| **Total** | **34** | **31** | **2** | **1** |

---

## Traceability — story to endpoint

| Story | Primary endpoints |
|---|---|
| US-1.1, US-1.2 | `POST /api/search`, `POST /api/search/stream`, `GET /api/objects/{type}/{id}` |
| US-1.3 | `POST /api/substitute`, `GET /api/substitute/sample-products` |
| US-1.4 | `POST /api/price/compare` |
| US-2.1, US-2.2 | `POST /api/safety-check`, `GET /api/safety/profiles` |
| US-2.3 | `GET /api/ops/guardrail` |
| US-3.1, US-3.2 | `POST /api/chat`, `GET /api/ops/memory`, `GET /api/ops/trace` |
| US-3.3 | `POST /api/insights`, `POST /api/insights/stream` |
| US-3.4 | `POST /api/logistics/nearest`, `GET /api/logistics/{inventory,shortest-path}` |
| US-4.1 | `POST /api/persona-match`, `GET /api/personas` |
| US-4.2 | `GET /api/churn/{dashboard,map,member/{id}}` |
| US-4.3 | `GET /api/acquisition/dashboard` |
| US-4.4 | `GET /api/tier-up/{dashboard,map}` |
| US-5.1, US-5.2 | `GET /api/vip/{opportunity,loyal,whale,cross-category,trajectory}` |
| US-6.1 | `GET /api/logistics/{network,status,events,warehouse/{id}}` |
| US-6.2, US-6.3 | `GET /api/coverage/dashboard` |
| US-7.1 | `GET /api/objects/{type}`, `GET /api/objects/{type}/{id}` |
| US-7.2, US-7.3 | `GET /api/ontology/{schema,standards,validation}` |
| US-8.1, US-8.2, US-8.3 | `GET /api/ops/{ingest,eval,cost}` |
| US-8.5 | `GET /api/auth/{login,callback,whoami,logout}`, `GET /healthz` |
