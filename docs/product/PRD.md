# Product Requirements Document — Ontology Retail Intelligence Platform

**Product name (working):** Ontology Retail — Korean Retail/CPG Knowledge Graph Intelligence Platform
**Codebase:** `ontology-retail` · **Version at time of writing:** v0.7.0 (+ Unreleased codegraph)
**Live demo:** https://retail-ontology.whchoi.net
**Document owner:** Product / Solutions
**Last updated:** 2026-08-31
**Status:** Deployed reference implementation — production-hardening checklist in §12

---

## 1. Executive summary

Retailers and CPG brands in Korea sit on data that is *individually* well managed and *collectively*
unusable. Product master data lives in the PIM. Ingredients and regulatory classifications live in
compliance spreadsheets. Member RFM lives in the CRM. Campaign response lives in the marketing
automation tool. Inventory and lanes live in the WMS/TMS. External consumption panels arrive as
quarterly PDFs from a research agency.

Every interesting question a merchandiser, marketer, or supply-chain planner asks crosses **four or
more** of those systems — so it becomes a two-week analyst request instead of a two-second answer.

**Ontology Retail** collapses those silos into a single governed knowledge graph and puts thirteen
decision surfaces on top of it, each answerable in natural Korean, each returning not just an answer
but the *path through the graph* that justifies it.

The platform is built entirely on AWS managed services — Amazon Neptune, OpenSearch Serverless,
Amazon Bedrock (Claude Sonnet 4.6, Cohere embed/rerank), Bedrock AgentCore (Memory + Code
Interpreter), ECS Fargate, CloudFront + Cognito — with the full infrastructure defined as AWS CDK
code across six stacks.

**The core claim:** one ontology, thirteen revenue-relevant scenarios, zero data-team tickets.

---

## 2. Problem statement

### 2.1 Business problems addressed

| # | Problem | Today's cost | What the platform changes |
|---|---------|--------------|---------------------------|
| P1 | **Search does not understand intent.** "임산부가 써도 되는 저자극 선크림" returns keyword noise. | Lost conversion; merchandising blind spots. | Korean-analyzer BM25 + dense vectors + reranking, grounded in an ingredient/concern ontology. |
| P2 | **Safety & compliance checks are manual.** Pregnancy, pediatric, allergen suitability is judged by a person reading an INCI list. | Regulatory risk; slow assortment onboarding. | Deterministic graph traversal over INCI/KFDA/FoodOn mappings + Bedrock Guardrails. |
| P3 | **Merchandisers can't self-serve analytics.** Trend questions become BI backlog items. | 1–2 week latency per question. | Natural-language MD Insights with live chart generation in a sandbox. |
| P4 | **Churn is discovered after it happens.** | Retained revenue left on the table. | RFM-derived churn risk precomputed per member, sliceable by tier, persona and region. |
| P5 | **Marketing spend attribution is channel-blind.** | Misallocated acquisition budget. | Campaign × Channel × Persona ROI matrix from touchpoint-level attribution. |
| P6 | **Tier-up levers are guesswork.** | Weak loyalty programme economics. | Statistical lift of every product/category on Silver→Gold conversion. |
| P7 | **Logistics and membership are analysed separately.** | Service-level blind spots in underserved regions. | One choropleth joining member density, churn, LTV and warehouse coverage radius. |
| P8 | **Wallet share is unknown.** Internal transactions only show *our* share of a customer's spend. | VIP targeting optimises the wrong customers. | External consumption panel bridged to internal categories — five wallet-share-aware VIP definitions. |

### 2.2 Why a knowledge graph, and not a data warehouse

A warehouse answers *aggregate* questions well and *relationship* questions badly. The questions in
this product are relationship questions:

- "Which ingredient, present in a product this persona already buys, is the reason a similar product
  is unsafe for her?" — 4 hops.
- "Which members live more than 50 km from any warehouse *and* match the camper persona *and*
  have rising external spend in outdoor gear?" — a join across membership, geography, logistics and
  a third-party panel.

Those are one Cypher statement on a graph and a multi-CTE nightmare in SQL. The graph is also what
makes the LLM answers *explainable*: every answer ships with the subgraph that produced it.

---

## 3. Goals and non-goals

### 3.1 Goals

- **G1 — One coherent context.** A single persona selection propagates across all thirteen scenarios.
- **G2 — Explainable AI.** Every generated answer is accompanied by the graph path, source rows, or
  tool-call trace that produced it.
- **G3 — Korean-first.** Nori analyzer, Korean embeddings, Korean chart glyphs (NanumGothic),
  KOSTAT administrative geography, KFDA/GS1 category mapping.
- **G4 — Managed-service-only.** No self-managed model serving, no self-managed vector store, no
  self-managed graph engine. Operating burden stays with AWS.
- **G5 — Infrastructure as code.** Every resource reproducible via `cdk deploy --all` in a new account.
- **G6 — Demonstrable in 30–60 minutes.** A guided tour walks a stakeholder through all thirteen
  scenarios without a script.

### 3.2 Non-goals (v1)

- **NG1** — Not a replacement for the PIM, CRM, WMS or campaign manager. It is a *read-side* semantic
  layer over them.
- **NG2** — No transactional writes back into source systems. Recommendations are surfaced, not executed.
- **NG3** — No real-time streaming ingestion in v1. Data lands via a batch loader.
- **NG4** — Not multi-tenant in v1. One deployment = one retailer.
- **NG5** — No mobile-native client. Responsive web only.

---

## 4. Target users and personas

### 4.1 Buying personas (who signs)

| Persona | Title | Primary pain | What wins the deal |
|---|---|---|---|
| **The Digital Officer** | CDO / Head of Digital Transformation | "We bought Neptune/Bedrock, we have no flagship use case." | Thirteen working scenarios on their own domain, deployed by CDK in days. |
| **The Merchandising Lead** | MD 본부장 | Analyst backlog; assortment decisions made on gut feel. | Scenario C + F + G — self-serve, chart-backed, in Korean. |
| **The CRM Lead** | 멤버십/CRM 담당 임원 | Churn and tier-up levers invisible; VIP list is just "top LTV". | Scenarios I, J, K, M — especially wallet share (M). |
| **The Supply Chain Lead** | SCM 본부장 | Coverage gaps found only after SLA breaches. | Scenarios H + L on one map. |
| **The Compliance Officer** | 품질/규제 담당 | Manual INCI/KFDA review, personal liability. | Scenario E — deterministic, auditable, guardrailed. |

### 4.2 Demo spine personas (the data model's five archetypes)

Every scenario is coherent for the same five shopper archetypes:

1. **임산부 (Pregnant)** — avoids retinoid/salicylic-class ingredients, high safety sensitivity.
2. **4세 아이 엄마 (Parent of a 4-year-old)** — pediatric safety, baby-food category, 경기 region skew.
3. **캠퍼 (Camper)** — outdoor/BBQ categories, 강원 region skew, strong external-spend blind spot.
4. **민감성 피부 (Sensitive skin)** — skincare-heavy, ingredient-avoidance driven.
5. **글루텐 알레르기 (Gluten allergy)** — allergen filtering across grocery.

Forty richer *narrative* personas sit above the spine and bridge to it via `DERIVED_FROM`, so a
narrative persona selection still resolves to spine-linked members and transactions.

---

## 5. Product capabilities (the thirteen scenarios)

Each scenario is a distinct page, a distinct API surface, and a distinct decision it supports.

### A — Semantic Search (`/search`)
Korean natural-language query → OpenSearch BM25 with the **Nori** Korean analyzer, in parallel with
Cohere `embed-v4` 1024-dim KNN vector search → **reciprocal-rank fusion** → **Cohere `rerank-v3`**
cross-encoder reranking → results rendered with a **1-hop knowledge subgraph** showing why each SKU
matched (ingredient, concern, trend, brand).
*Decision supported:* assortment discovery, on-site search quality benchmarking.
*Endpoints:* `POST /api/search`, `POST /api/search/stream`.

### B — Conversational Agent (`/chat`)
Bedrock Converse multi-turn on Claude Sonnet 4.6, with **AgentCore Memory** providing short-term
session recall and long-term user-namespaced facts (7-day TTL). Seven registered tools including
`memory_recall`, `neptune_subgraph`, `semantic_search`, `kb_lookup`, `inventory_lookup`,
`nearest_warehouses`, `shortest_path`. Streams over SSE with a **live tool-call panel** so the
audience sees every tool invocation and its arguments.
*Decision supported:* conversational commerce, internal copilot.
*Endpoint:* `POST /api/chat` (SSE).

### C — MD Insights (`/insights`)
Neptune trend aggregation runs **first** (Trend↔Ingredient rollup, ranked by fanout), then Sonnet 4.6
produces a **token-streamed Korean summary** over those rows — the system prompt explicitly forbids
inventing numbers not present in the data. The endpoint returns a `chart_spec`
(`{type, title, data[]}`) computed from the same aggregation, which the client renders; the chart is
therefore derived from the graph, not generated by the model. If Bedrock is unavailable, a
deterministic recap is built from the same rows so the page still has narrative.

> `api/services/code_interpreter.py` (AgentCore Code Interpreter + matplotlib + NanumGothic) is
> implemented but **not yet wired into this route** — no router imports it. Server-side PNG chart
> rendering is built and ready, pending a route change; see the readiness checklist (§12).
*Decision supported:* category trend reviews, weekly MD meetings.
*Endpoints:* `POST /api/insights`, `POST /api/insights/stream`.

### D — Persona Match (`/match`)
Graph walk across `HAS_CONCERN` → preferred/avoided ingredients → weighted SKU recommendation across
forty synthetic personas.
*Decision supported:* personalised merchandising, segment-level assortment.
*Endpoints:* `POST /api/persona-match`, `GET /api/personas`.

### E — Safety Lens (`/safety`)
Profile-driven filtering (pregnancy / pediatric / gluten-free / vegan / sensitive skin) combining
**Bedrock Guardrails** with deterministic `AVOIDS_INGREDIENT` traversal over **INCI** and **KFDA**
ingredient mappings. Violations are highlighted with the offending ingredient named.
*Decision supported:* compliance sign-off, product-detail-page safety badges.
*Endpoints:* `POST /api/safety-check`, `GET /api/safety/profiles`.

### F — Substitute Finder (`/substitute`)
Same-category, cross-brand traversal weighted by ingredient and concern overlap, presented as
price-delta cards.
*Decision supported:* out-of-stock substitution, private-label switching, margin optimisation.
*Endpoints:* `POST /api/substitute`, `GET /api/substitute/sample-products`.

### G — Price & Availability Compare (`/price`)
Natural language → recommended SKU → four-channel matrix (CU 편의점 / 이마트 / 올리브영 / 마켓컬리)
of price, discount and stock, weighted by persona–channel affinity.
*Decision supported:* competitive pricing, channel strategy.
*Endpoint:* `POST /api/price/compare`.

### H — Logistics Network (`/logistics`)
Korean choropleth (react-simple-maps + d3-geo over KOSTAT 17-시도 GeoJSON) showing **30 warehouses,
76 lanes, 940 inventory rows**, a KPI strip (OTD rate, active shipments, transit time, exceptions,
active events), and an **inline LLM panel** answering natural-language logistics questions via
`inventory_lookup`, `nearest_warehouses` (haversine k-NN) and `shortest_path` (BFS over route edges).
*Decision supported:* network design, disruption response.
*Endpoints:* `GET /api/logistics/{network,status,events,warehouse/{id},inventory/sku/{id},inventory/wh/{id},shortest-path}`, `POST /api/logistics/nearest`.

### I — Churn Risk (`/churn`)
RFM-derived `churn_risk` precomputed per member (recency / frequency / monetary + tier correction),
with tier × persona breakdowns, a Top-30 at-risk drilldown carrying a 1-hop graph per member,
persona-aware winback recommendations, and a **17-시도 choropleth** keyed on average churn risk.
*Decision supported:* retention campaign targeting.
*Endpoints:* `GET /api/churn/dashboard`, `GET /api/churn/map`, `GET /api/churn/member/{id}`.

### J — Acquisition ROI (`/acquisition`)
Per-campaign and per-channel ROI (cost ÷ attributed LTV from *responded* touchpoints) plus a
**Persona × Channel response-rate heatmap** identifying the best channel per archetype — the
"카카오 push vs email" question answered with data.
*Decision supported:* acquisition budget allocation.
*Endpoint:* `GET /api/acquisition/dashboard`.

### K — Tier-up Path (`/tier-up`)
Silver→Gold **lift** per product and per category (per-capita Gold rate ÷ Silver rate with Laplace
smoothing), upgrade-candidate ranking (Silver members with LTV ≥ ₩1.5M sorted by gap-to-Gold), and a
17-시도 map keyed on candidate density.
*Decision supported:* loyalty programme design, targeted upgrade offers.
*Endpoints:* `GET /api/tier-up/dashboard`, `GET /api/tier-up/map`.

### L — Coverage Map (`/coverage`)
The hub scenario. Persona-filtered choropleth of member distribution by 시도, overlaid with warehouse
markers, a four-dimension toggle (member count / avg churn / avg LTV / uncovered share) and a radius
slider driving a single headline KPI: **"내 페르소나 회원 중 N km 안에 거점이 없는 비율"** — the share
of this persona's members with no fulfilment node within N km. Bridges membership · logistics ·
persona on one screen.
*Decision supported:* network expansion business cases.
*Endpoint:* `GET /api/coverage/dashboard`.

### M — VIP Target Builder (`/vip`) — the differentiator
Layers an **external consumption panel** (10 industry categories × 10,410 quarterly spend edges
across Q4 2025 + Q1 2026) above internal transactions, bridged through `OVERLAPS_WITH` edges to GS1
brick categories. This yields **wallet share** — `our_internal ÷ (our_internal + external)` — per
member per category, and with it five simultaneous, tunable VIP definitions:

| Axis | Definition | Marketing action |
|---|---|---|
| **Opportunity** | Low our-share, high total category spend | Highest untapped ₩ upside — offensive targeting |
| **Loyal** | Our-share ≥ 0.5, total ≥ ₩300k | Majority defenders — defensive retention |
| **Whale** | tier = VIP and LTV ≥ ₩5M | Concierge / high-touch |
| **Cross-category** | Buys one internal category only, but large external spend in a *non-overlapping* industry | Category extension — tells you *which* industry to extend into |
| **Trajectory** | Q1/Q0 growth ≥ 1.2× and tier ≠ VIP | "Future VIPs" — early upgrade offers |

Two of the ten industries (생활용품, 캠핑 장비) carry **deliberate 0% wallet share** — the strongest
possible Opportunity signal, and the clearest demonstration of what internal-data-only VIP scoring
cannot see.
*Decision supported:* VIP programme definition, share-of-wallet growth strategy.
*Endpoints:* `GET /api/vip/{opportunity,loyal,whale,cross-category,trajectory}`.

### Supporting surfaces

- **Knowledge Graph Object Explorer** (`/objects/{type}`) — browsable, drill-downable views of all
  **21 registered node types**, each ranked by graph fan-out, each instance showing its 1-hop
  neighbourhood.
- **Ontology Meta** (`/schema`, `/standards`, `/validation`) — Cytoscape ER diagram of the ontology,
  standards-mapping CSV browser (INCI / FoodOn / GS1↔KFDA), and a validation coverage report.
- **Operations Console** (`/ops`) — ingest counts, guardrail intervention log, AgentCore memory
  snapshots, evaluation pass-rate scoreboard, tool-call trace timeline, and cost view.
- **Code Knowledge Graph** (`/codegraph`, meta) — the platform pointed at *itself*: an AST-derived
  graph of 1,751 nodes / 2,217 edges / 159 communities across 151 source files, with each community
  labelled offline by Bedrock Sonnet 4.6 into structured JSON (label / description / key concepts /
  top files). Proof that the ontology approach generalises beyond retail.
- **Guided Tour** — a five-minute in-app walkthrough covering every scenario.
- **Persona Switch** — global persona selector; every scenario re-slices to it.
- **Configurable company logo** — four bundled SVG presets, click-to-cycle, `localStorage`-persisted,
  build-time default override. Rebrand the demo for a customer meeting in one click.

---

## 6. The ontology (data model)

### 6.1 Five layers

| Layer | Phase | Node types |
|---|---|---|
| **Commerce core** | 1 | Product, Brand, Manufacturer, Category (GS1 brick), Ingredient, Nutrient |
| **Lifestyle** | 2 | Persona, Concern, Trend, Review, Channel, Promotion |
| **Logistics** | 5 | Region, Warehouse, Carrier, Route, Shipment, Event, Inventory |
| **Membership & marketing** | 2A / 2A-G | Member, MembershipTier, Campaign, Transaction, Touchpoint (+ `LIVES_IN` geography) |
| **External consumption** | 2B | IndustryCategory, `HAS_CATEGORY_SPEND`, `OVERLAPS_WITH` |

### 6.2 Reference data volumes (demo dataset)

| Entity | Count | Entity | Count |
|---|---|---|---|
| Products | 250 | Members | 1,000 |
| Brands | 60 | Membership tiers | 4 |
| Manufacturers | 30 | Campaigns | 20 |
| Personas (narrative) | 40 | Transactions | 7,862 |
| Personas (spine) | 5 | Touchpoints | 10,021 |
| Reviews | 2,480 | Industry categories | 10 |
| Channels | 4 | External spend edges | 10,410 |
| Regions (KOSTAT 시도) | 17 | Category overlap edges | 43 |
| Warehouses | 30 | Lanes | 76 |
| Carriers | 7 | Inventory rows | 940 |
| Disruption events | 12 | FoodOn aliases | 219 |

Approximately **5,000 nodes and 10,000 edges** in the commerce+logistics core, plus the membership
and external layers on top.

### 6.3 Determinism guarantee

All synthetic identifiers and probabilities derive from a **SHA-1-seeded PRNG**, and every date is
computed relative to a fixed `ANCHOR_DATE = 2026-04-01`. The same seed produces the same graph, so a
reload before a customer demo never changes the story — and evaluation results stay comparable across
runs.

### 6.4 Standards alignment

- **INCI** — cosmetic ingredient nomenclature, drives the safety lens for beauty SKUs.
- **FoodOn** — food ontology, 219 Korean aliases mapped.
- **GS1 brick codes ↔ KFDA category paths** — the bridge that makes regulatory category and retail
  category the same query.

Mappings are versioned CSV/JSON under `ontology/mappings/` and browsable in-app under `/standards`,
with per-standard coverage shown at `/validation`.

---

## 7. Architecture

### 7.1 Request path

```
Browser (retail-ontology.whchoi.net)
  → CloudFront  [ACM TLS · Lambda@Edge cookie auth · X-Origin-Auth-Token injection]
  → ALB         [SG restricted to the CloudFront origin-facing prefix list]
  → ECS Fargate ARM64
       ├─ web : Next.js 14 App Router, standalone output, 2 replicas
       └─ api : FastAPI + uvicorn, 2 replicas
  → Amazon Neptune (openCypher, SigV4) · OpenSearch Serverless (Nori BM25 + KNN)
  → Amazon Bedrock (Sonnet 4.6 · Cohere embed-v4 · Cohere rerank-v3 · Guardrails · Knowledge Base)
  → Bedrock AgentCore (Memory · Code Interpreter)
  ← SSE stream back to the browser
```

### 7.2 Technology choices

| Layer | Choice | Rationale |
|---|---|---|
| Graph | Amazon Neptune, openCypher | Managed, IAM-authenticated, VPC-private; Cypher is the shortest path from question to answer. |
| Search | OpenSearch Serverless | Nori analyzer is the reference Korean tokenizer; serverless removes cluster ops. |
| Fusion | RRF + Cohere rerank-v3 | Lexical recall + semantic recall, then a cross-encoder for precision. Falls back to RRF order on any reranker error. |
| Chat / insights | Claude Sonnet 4.6 via Bedrock Converse | Korean fluency and tool-use reliability. Explicit project rule: never silently downgrade to a lighter model. |
| Charts | Aggregation-derived `chart_spec`, client-rendered | Chart values come from the Neptune rollup, not the model. AgentCore Code Interpreter (server-side matplotlib in a Firecracker microVM) is implemented but not yet wired to a route. |
| Memory | AgentCore Memory | Managed short-term session + long-term user namespaces; no bespoke memory store. |
| Compute | ECS Fargate ARM64 (Graviton) | Price/performance; no node management. |
| Edge/auth | CloudFront + Lambda@Edge + Cognito | Auth enforced at the edge, before any origin request. |
| IaC | AWS CDK v2 (TypeScript), 6 stacks | Network · Data · Compute · AI · Edge · Observability. |

### 7.3 Notable engineering decisions (13 ADRs on file)

Decisions are recorded as numbered ADRs in `docs/decisions/`, including: AgentCore Memory
provisioning via `AwsCustomResource` (0001), CloudTrail via L1 `CfnTrail` (0002), Lambda@Edge stable-ID
baking (0003), Cognito client authored exclusively through CDK because `update-user-pool-client` has
PUT semantics (0004), the narrative↔spine persona bridge (0005/0006), member region distribution
(0007), the wallet-share VIP framework (0008), the Phase 2B data model (0009), codegraph community
labelling (0010/0013), and the Lambda@Edge root gate and logout flow (0012).

---

## 8. Functional requirements

| ID | Requirement | Scenario |
|---|---|---|
| FR-01 | The system SHALL accept free-form Korean queries and return ranked SKUs with the graph path that justified each match. | A |
| FR-02 | The system SHALL maintain multi-turn conversational context across a session and recall long-term user facts across sessions. | B |
| FR-03 | The system SHALL stream every LLM response token-by-token and emit a structured event per tool call. | B, C |
| FR-04 | The system SHALL derive every charted value from a graph aggregation rather than from model output. | C |
| FR-05 | The system SHALL evaluate SKU suitability against a named safety profile and name the specific violating ingredient. | E |
| FR-06 | The system SHALL apply Bedrock Guardrails to chat input and insights output. | B, C, Ops |
| FR-07 | The system SHALL compare price, discount and stock across at least four retail channels for a given SKU. | G |
| FR-08 | The system SHALL compute nearest-warehouse (haversine k-NN) and shortest-path (BFS over lanes) results on demand. | H |
| FR-09 | The system SHALL precompute churn risk per member from RFM and expose it sliced by tier, persona and region. | I |
| FR-10 | The system SHALL attribute campaign cost to responded touchpoints and report ROI by campaign, channel and persona. | J |
| FR-11 | The system SHALL compute Silver→Gold lift per product and category with Laplace smoothing. | K |
| FR-12 | The system SHALL report the share of a persona's members with no fulfilment node within an operator-chosen radius. | L |
| FR-13 | The system SHALL compute per-member per-category wallet share by joining an external consumption panel to internal transactions. | M |
| FR-14 | The system SHALL expose five independently tunable VIP definitions over the same underlying data. | M |
| FR-15 | A single persona selection SHALL propagate to every scenario without re-selection. | All |
| FR-16 | The system SHALL expose every registered node type through a browsable explorer with 1-hop neighbourhood drilldown. | Objects |
| FR-17 | The system SHALL expose ingest counts, guardrail interventions, memory contents, evaluation scores and tool traces to an operator. | Ops |
| FR-18 | All Cypher SHALL be parameterised; no user input is ever string-interpolated into a query. | All |

---

## 9. Non-functional requirements

| ID | Requirement | Current status |
|---|---|---|
| NFR-01 | **Availability** — no single point of failure in the application tier. | Two Fargate replicas per service behind an ALB across private subnets. |
| NFR-02 | **Latency** — interactive scenarios return first token / first paint within a demo-acceptable window. | All analytical scenarios read precomputed node properties (e.g. `churn_risk`) so router work is sort/filter only. |
| NFR-03 | **Reproducibility** — a new AWS account reaches a working deployment from source. | `cdk bootstrap` + `cdk deploy --all` + one-shot loader ECS task. |
| NFR-04 | **Determinism** — the same data load produces the same demo. | SHA-1-seeded PRNG + fixed anchor date. |
| NFR-05 | **Observability** — CloudWatch logs per service, ALB access logs, CloudTrail management events, cost anomaly detection, account-level alarms on Bedrock error rate / Neptune CPU / OpenSearch search rate. | Implemented in the Observability stack (see §12 for the deferred items). |
| NFR-06 | **Regionality** — all inference and data services in `ap-northeast-2` (Seoul), except Lambda@Edge and the CloudFront ACM certificate which are necessarily `us-east-1`. | Implemented. |
| NFR-07 | **Cost control** — no always-on GPU, no provisioned model throughput, serverless search. | Implemented; `/ops` exposes a 7-day cost view. |
| NFR-08 | **Accessibility & i18n** — Korean-first UI with English documentation parity. | README, CHANGELOG, architecture doc all bilingual. |

---

## 10. Security

**Implemented today**

- **Edge authentication** — Lambda@Edge performs a cookie check on every request. The public-path
  whitelist is deliberately narrow (`callback`, `logout`, `_next`, `favicon`, `api/health`); the root
  path `/` is gated, so an anonymous visitor gets a 302 to the Cognito Hosted UI rather than a
  half-rendered SPA shell (ADR-0012).
- **Identity** — Cognito user pool, OAuth authorisation-code grant, self-signup disabled,
  admin-provisioned users. The API performs **complete RS256 verification**: signature against the
  `kid`-matched JWK from Cognito's JWKS endpoint, issuer, expiry/not-before, and audience
  (`client_id` for access tokens, `aud` for id tokens). JWKS is cached with a 1-hour TTL so key
  rotation cannot permanently reject freshly signed tokens.
- **Origin isolation** — the ALB security group admits only the AWS-managed
  `com.amazonaws.global.cloudfront.origin-facing` prefix list. Direct internet→ALB is impossible.
- **Origin authentication** — CloudFront forwards a Secrets-Manager-backed `X-Origin-Auth-Token`,
  compared in constant time at the API. Enforced today: the API task definition sets
  `REQUIRE_ORIGIN_AUTH=true`, so a request that does not come through CloudFront is rejected.
- **Private data plane** — Neptune, OpenSearch and Aurora sit in private subnets with no public route.
- **Injection safety** — all Cypher parameters are passed as bound parameters, never interpolated.
- **Content safety** — Bedrock Guardrails on chat input scrubbing and insights output; interventions
  are logged and visible in the Operations console.
- **Secret hygiene in development** — a repository hook blocks AWS access keys, JWTs, private keys and
  vendor tokens from entering tool input or output, backed by a 60-entry command deny list.

**Documented trade-offs** — `SECURITY.md` records each accepted demo posture with its severity, its
compensating control, and the exact migration trigger. See §12.

---

## 11. Quality engineering

| Surface | Scope | Runtime |
|---|---|---|
| Python AST validation | `compileall` over `api`, `data`, `scripts` | ~1 s |
| TypeScript type-check | `web` and `infra-cdk` (matrix) | ~10 s |
| Pytest offline suite | 28 tests — 16 router-import smoke tests, Pydantic model validation, `/healthz`, `/api/search` integration with `httpx.AsyncClient` and boto3 mocked at the import site | <1 s |
| CDK snapshot tests | `Template.fromStack().toJSON()` for all 6 stacks — infrastructure drift detection | ~13 s |
| Live wow-query evaluation | Scenario-level query set against the deployed distribution; **exits non-zero below an 85% pass rate** | minutes |

CI (`.github/workflows/ci.yml`) runs four jobs on every push and pull request to `main` with
cancel-in-progress concurrency; the offline gate completes in under 13 seconds.

The engineering harness itself is scored against a twelve-dimension rubric; the most recent full
evaluation returned **8.8 / 10 (grade A)**, with perfect scores on safety, completeness, consistency,
context management and feedback-loop maturity.

---

## 12. Production-readiness checklist

The deployment is a **working reference implementation on real AWS managed services**, not a mockup.
The following items separate it from a customer-specific production rollout. Each is scoped and
unblocked — this list is the honest delta, and it is short.

| # | Item | Effort | Trigger |
|---|---|---|---|
| 1 | **Real customer data replaces the synthetic loader.** The graph shape stays; the loader is repointed at the customer's PIM / CRM / WMS extracts. | Weeks (integration-bound) | Contract signature |
| 2 | **CloudFront→ALB TLS.** Currently HTTP:80 on the origin hop, protected by prefix-list-only ingress plus the shared origin token. Requires an ACM cert on a customer-owned origin domain and a 443 listener. | ~1 day | Customer domain assigned |
| 3 | **`DEMO_PUBLIC_MODE=false`.** The API JWT middleware is implemented and defaults open for demo convenience. Flipping the ECS task env enforces it. | Minutes | Real users |
| 4 | **Optional: full signature verification at the edge.** The API already does complete RS256/JWKS verification; the Lambda@Edge gate checks token presence and expiry only. Promoting the edge check matters only if the edge must reject forged tokens unaided. | ~50 LOC | Threat model requires it |
| 5 | **CloudTrail Bedrock data events.** Model-invocation audit trail for compliance. | ~1 hour CDK | Compliance requirement |
| 6 | **ALB access logs to S3** with lifecycle to Glacier. | ~1 hour CDK | Forensics requirement |
| 7 | **CloudWatch Logs customer-managed KMS key.** Currently AWS-managed (a cross-stack KMS cycle was avoided); fix is relocating log groups to the Data stack. | ~2 hours CDK | Production deployment |
| 8 | **Multi-tenancy / RBAC.** Cognito groups (`shopper` / `md` / `admin`) are provisioned but not yet used for route-level authorisation. | ~1 week | Multi-department rollout |
| 9 | **Incremental / streaming ingestion.** v1 is a batch reload. | ~2 weeks | Data freshness SLA |
| 10 | **Neptune multi-AZ sizing.** Dev deployment is single-instance. | Config change | Production SLA |
| 11 | **Wire AgentCore Code Interpreter into `/api/insights`.** `api/services/code_interpreter.py` is implemented but unimported; wiring it adds server-rendered matplotlib PNGs alongside the current client-rendered `chart_spec`. | ~1 day | Richer chart types needed |

---

## 13. Success metrics

| Dimension | Metric | Target |
|---|---|---|
| **Answer quality** | Wow-query evaluation pass rate | ≥ 85% (CI-enforced) |
| **Self-service** | Analyst tickets displaced per month | ≥ 20 in the first quarter |
| **Retention** | Winback conversion on the Top-30 at-risk cohort vs. an untargeted control | +3pp |
| **Acquisition** | Blended CAC after reallocating spend to the best persona×channel cells | −10% |
| **Loyalty** | Silver→Gold conversion among ranked upgrade candidates vs. control | +5pp |
| **Wallet share** | Category wallet share among targeted Opportunity VIPs | +2pp per quarter |
| **Network** | Members outside the coverage radius | −15% after the first expansion decision |
| **Operations** | Guardrail interventions requiring human review | < 1% of sessions |
| **Adoption** | Weekly active internal users across MD / CRM / SCM | 3 teams by month 3 |

---

## 14. Roadmap

**Now (shipped, v0.7.0 + unreleased)**
Thirteen scenarios A–M · 21 explorable node types · ontology meta and validation surfaces ·
operations console · code knowledge graph · guided tour · configurable branding.

**Next (0–3 months)**
Production-readiness items 2–4 and 10 · customer data integration · Cognito group RBAC ·
scenario-level export (CSV / campaign-manager handoff) · scheduled snapshot of every dashboard to
email.

**Later (3–9 months)**
Write-back connectors (push a VIP segment straight into the campaign manager) · incremental ingestion ·
multi-tenant deployment model · scenario authoring UI so an analyst can define a new graph-backed
dashboard without a code change · time-travel on the graph for cohort-over-time comparison.

---

## 15. Open questions

1. **Data residency and PII** — will the customer's member records be pseudonymised before ingestion,
   or does the graph need field-level encryption for direct identifiers?
2. **External panel provenance** — which research agency supplies the consumption panel, at what
   cadence, and under what licence for derived storage?
3. **Category mapping ownership** — who owns the ongoing GS1↔KFDA↔internal category mapping once it
   drifts from the shipped CSVs?
4. **Action loop** — is v1 read-only, or is write-back into the campaign manager in scope for the
   first phase? This materially changes the security review.
5. **Model region** — is cross-region inference for the reranker acceptable under the customer's
   data-residency policy?

---

## Appendix A — API surface

Fifty endpoints across nineteen routers. Full request/response signatures in
[`docs/api-reference.md`](../api-reference.md).

| Group | Endpoints |
|---|---|
| Auth | `/api/auth/{login,callback,whoami,logout}` |
| Search (A) | `POST /api/search`, `POST /api/search/stream` |
| Chat (B) | `POST /api/chat` |
| Insights (C) | `POST /api/insights`, `POST /api/insights/stream` |
| Persona (D) | `POST /api/persona-match`, `GET /api/personas` |
| Safety (E) | `POST /api/safety-check`, `GET /api/safety/profiles` |
| Substitute (F) | `POST /api/substitute`, `GET /api/substitute/sample-products` |
| Price (G) | `POST /api/price/compare` |
| Logistics (H) | `GET /api/logistics/{network,status,events,warehouse/{id},inventory/sku/{id},inventory/wh/{id},shortest-path}`, `POST /api/logistics/nearest` |
| Churn (I) | `GET /api/churn/{dashboard,map,member/{id}}` |
| Acquisition (J) | `GET /api/acquisition/dashboard` |
| Tier-up (K) | `GET /api/tier-up/{dashboard,map}` |
| Coverage (L) | `GET /api/coverage/dashboard` |
| VIP (M) | `GET /api/vip/{opportunity,loyal,whale,cross-category,trajectory}` |
| Objects | `GET /api/objects/{type}`, `GET /api/objects/{type}/{id}` |
| Ontology | `GET /api/ontology/{schema,standards,standards/{file},validation}` |
| Operations | `GET /api/ops/{ingest,guardrail,memory,eval,trace,cost}` |
| Ingest | `POST /api/ingest/pdf` |
| Health | `GET /healthz` |

## Appendix B — Reference documents

| Document | Contents |
|---|---|
| `README.md` | Bilingual overview, install, usage, configuration |
| `docs/architecture.md` | Full component inventory, data flow, stack table |
| `docs/api-reference.md` | Endpoint signatures and payload shapes |
| `docs/membership.md` | Phase 2A membership layer design |
| `docs/aws-resources.md` | Deployed resource inventory |
| `docs/onboarding.md` | New-engineer ramp |
| `docs/decisions/0001–0013` | Architecture decision records |
| `docs/runbooks/` | Deploy, data reload, loader rollback, ECR auth refresh, codegraph refresh |
| `SECURITY.md` | Security posture, accepted trade-offs, migration triggers |
| `CHANGELOG.md` | Bilingual release history |
