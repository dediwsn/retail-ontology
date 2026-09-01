# Architecture

<p align="center">
  <kbd><a href="#english">English</a></kbd> · <kbd><a href="#한국어">한국어</a></kbd>
</p>

---

# English

## System Overview

`ontology-retail` is a multi-tier AWS-native demo for a Korean Retail/CPG knowledge graph. A FastAPI backend on Fargate fronts Bedrock + AgentCore + Neptune + OpenSearch, while a Next.js 14 frontend on Fargate provides scenario-specific UIs. CloudFront with Lambda@Edge cookie auth wraps the entire surface and a Cognito user pool gates access.

Thirteen wow scenarios (A–M) span semantic search, conversational agent with memory, MD insights, persona match, safety, substitution, price/availability comparison, logistics network, churn diagnosis, acquisition ROI, tier-up path, member-warehouse coverage map, and **VIP target builder with 5-axis wallet-share analysis**. The ontology covers five layers — commerce/lifestyle (Phase 1–2), logistics (Phase 5), membership/marketing (Phase 2A), member geography (Phase 2A-G), and **external consumption panel (Phase 2B)** — with two Korean choropleth views (`react-simple-maps` + d3-geo + KOSTAT 행정구역 GeoJSON) shared across H/I/K/L. A separate `/codegraph` meta page embeds the graphify-generated AST graph, with 159 communities labelled offline via Bedrock Sonnet 4.6 (4-field structured-JSON output: label, description, key_concepts, top_files).

## Components by Layer

### Edge & Auth

- **CloudFront distribution** (`<distribution-id>`) — TLS termination, viewer/origin caching, custom domain `retail-ontology.<your-domain>` with an ACM `*.<your-domain>` cert (set via `PUBLIC_DOMAIN` + the CloudFront alias; the original reference deployment used `whchoi.net`).
- **Lambda@Edge** (`AuthEdgeFn`, us-east-1 `experimental.EdgeFunction`) — cookie-based auth check on every request. `PUBLIC_PATHS` whitelist (`callback`, `logout`, `_next`, `favicon`, `api/health`) is intentionally narrow — the root path `/` is gated, so anonymous viewers see a 302 to Cognito Hosted UI immediately, not a half-loaded SPA shell. See [ADR-0012](decisions/0012-lambda-edge-root-gate-and-logout.md).
- **Cognito User Pool** (`<user-pool-id>`) — RS256 JWTs, OAuth code grant, email-as-username, demo password policy (8 chars). Hosted UI logout URL must include `https://<PUBLIC_DOMAIN>/` (with trailing slash) for `/api/auth/logout` to land cleanly.
- **Auth router** (`api/routers/auth.py`) — `/api/auth/login` (sidebar re-auth), `/api/auth/callback` (OAuth code → token exchange + cookie set), `/api/auth/logout` (cookie clear + Cognito Hosted UI logout 302), `/api/auth/whoami` (always JSON 200, `{authenticated: bool, ...}`).
- **Origin Auth** — CloudFront forwards a Secrets-Manager-backed `X-Origin-Auth-Token` header to ALB; ALB SG restricts ingress to `com.amazonaws.global.cloudfront.origin-facing`.

### Compute

- **Web service** (ECS Fargate ARM64) — Next.js 14 standalone build, two-replica behind ALB.
- **API service** (ECS Fargate ARM64) — FastAPI + uvicorn, two-replica, same image used as a one-shot loader via command override.
- **ALB** (`ontology-retail-dev-alb`) — HTTP-80 origin (TLS terminated at CloudFront for demo posture; production cutover documented in SECURITY.md).

### Data & Search

- **Neptune cluster** (`ontology-retail-dev-neptune`) — single-instance dev sizing, openCypher endpoint, IAM auth via SigV4. 19 node classes (commerce + logistics + events) with ~5,000 nodes, ~10,000 edges loaded via the one-shot ECS loader.
- **OpenSearch Serverless collection** (`<opensearch-collection-id>`) — Nori Korean analyzer for BM25, Cohere `embed-v4` 1024-dim KNN, RRF fusion.
- **Aurora PostgreSQL Serverless v2** (`ontology-retail-dev-aurora`) — session metadata + Cognito linkage.
- **S3 buckets** — `raw-docs` (KB ingestion source), `uploads` (user uploads), `synthetic-data` (loader source — products/reviews/personas + regions/warehouses/carriers/routes/shipments/events/inventory), `ontology-snapshots` (versioned ontology).

### Logistics & Events (Phase 5)

- **Region / Warehouse / Carrier / Route / Shipment / Event / Inventory** — first-class graph nodes with edges `LOCATED_IN`, `OPERATES`, `FULFILLED_BY`, `FROM`/`TO`, `CARRIED_BY`, `VIA`, `CONTAINS`, `AFFECTS_REGION`, `AFFECTS_CATEGORY`, `HELD_AT`, `OF_SKU`.
- **Korean map** — react-simple-maps + d3-geo, `web/public/korea-provinces.json` (KOSTAT 17 시도, 146 KB), 5:4 viewBox preserves peninsula aspect at lat~36°N.
- **Inventory model** — first-class `Inventory` node (`{wh_id, sku_id, on_hand_pallets, capacity_pallets, days_of_cover, temperature}`) so graph traversal, validation, and time-series extension all stay natural. Avoids edge-property gotchas in openCypher.
- **Logistics agent tools** — `inventory_lookup`, `nearest_warehouses` (haversine k-NN), `shortest_path` (BFS over Route edges) registered in `api/services/agent.py:TOOL_SPECS`, callable from both the main chat (B) and the inline panel on `/logistics`.

### Membership & Marketing (Phase 2A + Phase 2A-G)

- **Member / MembershipTier / Campaign / Transaction / Touchpoint** — five new node types beneath the 5-persona spine. Edges: `BELONGS_TO`, `MATCHES_PERSONA`, `PREFERS_CHANNEL`, `MADE`, `OF_PRODUCT`, `HAS_TOUCHPOINT`, `FROM_CAMPAIGN`, `TARGETS`. Volumes: 1,000 members · 4 tiers · 20 campaigns · 7,862 transactions · 10,021 touchpoints.
- **Persona spine + narrative bifurcation** — 5 spine personas (`per_pregnant`, `per_kid_4yo_mom`, `per_camper`, `per_sensitive_skin`, `per_gluten_allergy`, all `is_spine=true`) drive segment scenarios; 40 narrative `psn_*` personas drive the persona-match scenario. `(narrative)-[:DERIVED_FROM]->(spine)` edges (10, computed from label-keyword matching at load time) bridge them so any persona selection in the UI resolves through `MATCHES_PERSONA` ➝ spine ➝ Member.
- **Member geography (Phase 2A-G)** — `(Member)-[:LIVES_IN]->(Region)` with persona-biased KOSTAT 17-sido distribution (camper×3.0 강원, kid_4yo_mom×2.0 경기, …). Reuses the same `Region` nodes that logistics created, sharing the choropleth view.
- **Scenarios** — I (`/churn` + `/api/churn/*`) RFM dashboard with map tab, J (`/acquisition` + `/api/acquisition/dashboard`) Campaign × Channel × Persona ROI matrix, K (`/tier-up` + `/api/tier-up/*`) Silver→Gold lift with map tab, L (`/coverage` + `/api/coverage/dashboard`) member-warehouse coverage hub. All four respect the active persona via `MATCHES_PERSONA` OR DERIVED_FROM-bridged 1-hop traversal.

### External Consumption (Phase 2B — Scenario M / VIP)

- **IndustryCategory** — 10 industry-level nodes (스킨케어 / 메이크업 / 바디·선케어 / 음료·티 / 건강기능식품 / 영유아 식품 / 캠핑·BBQ 식품 / 일반 식료품 / 생활용품 / 캠핑 장비). 8 of them carry `OVERLAPS_WITH` edges to existing GS1 brick `Category` nodes (43 edges total); 2 are deliberate "blind spots" (household, outdoor) where our wallet share = 0% — strongest Opportunity-VIP signal.
- **(Member)-[:HAS_CATEGORY_SPEND {amount_krw, period}]->(IndustryCategory)** — 10,410 edges = Q1 2026 (5,205) + Q4 2025 (5,205). Persona-biased generation (camper×3.5 outdoor, pregnant×2.5 baby food, sensitive×2.5 skincare, etc.) plus per-member growth factor (25% strong / 35% mild / 30% flat / 10% declining) so the Trajectory VIP can compute Q1/Q0 ratios.
- **5-axis VIP definitions** — Opportunity (low share / high total) · Loyal (share≥0.5 / total≥300k) · Whale (tier=VIP / LTV≥5M) · Cross-category (single internal cat + big external) · Trajectory (Q1/Q0 ≥ 1.2 / tier≠VIP). All 5 share a generic `CandidatesTable<T>` on the frontend and a `_persona_filter_fragment()` helper on the backend. See ADR-0008 / 0009.
- **Scenario M page** (`/vip` + `/api/vip/*`) — 5 tabs, persona-aware via the same OR-pattern, all 5 reachable from a single PersonaSwitch toggle.

### Code Knowledge Graph (`/codegraph` — meta)

- **graphify static bundle** — `web/public/codegraph/{graph.html, graph.json, manifest.json, GRAPH_REPORT.md}`. AST-only extraction, no LLM at build time. Current snapshot: 1,751 nodes / 2,217 edges / 159 communities / 151 source files.
- **Bedrock Sonnet 4.6 community labelling** — `scripts/label_codegraph_communities.py` produces `community_labels.json` + `community_meta.json` with 4-field structured JSON per community (label / description / key_concepts / top_files). graph.html is patched in-place to replace `community_name: "Community NNN"` with the semantic label (1,751 occurrences).
- **One-shot refresh** — `scripts/refresh_codegraph.sh` chains graphify update → bundle copy → Bedrock label → graph.html in-place patch. Step 4 patches *both* `RAW_NODES[].community_name` (node detail tooltip) and `LEGEND[].label` (always-visible right-hand legend) so all surfaces show the semantic label, not the raw `Community <N>` ID. Runtime ~3 min including 159 Bedrock calls. See ADR-0010 + [ADR-0013](decisions/0013-codegraph-legend-label-patch.md).

### AI & Memory

- **Bedrock Sonnet 4.6** — chat and insights (project decision: never Haiku Lite).
- **Bedrock Cohere embed-v4** — query and document embeddings.
- **Bedrock Cohere rerank-v3** — cross-region inference profile, optional with RRF fallback.
- **Bedrock Knowledge Base** (`<knowledge-base-id>`) — managed RAG retrieval over `raw-docs`.
- **Bedrock Guardrails** (`<guardrail-id>`) — input/output PII scrub for chat and insights.
- **AgentCore Memory** (`ontology_retail_dev_memory-<suffix>`) — short-term session events + long-term user-namespaced facts, 7-day TTL.
- **AgentCore Code Interpreter** — Firecracker microVM wrapper for matplotlib chart rendering with a bundled NanumGothic font, at `api/services/code_interpreter.py`. **Not currently wired into any route** — no router imports it (`grep -rn code_interpreter api/routers/`). Scenario C instead returns a `chart_spec` derived from the Neptune aggregation and renders it client-side. Wiring this in is tracked as a roadmap item.

### Observability & Safety

- **CloudTrail** — management events only (data events for Bedrock are not a CloudTrail event type).
- **CloudWatch Logs** — `/aws/ecs/ontology-retail-dev/api`, `/aws/ecs/ontology-retail-dev/web`, AWS WAF logs.
- **ALB Access Logs** — S3-stored, lifecycle to Glacier after 30 days.
- **Cost Anomaly Detection** — `Default-Services-Monitor` subscription with email notification.
- **Account-level CloudWatch Alarms** — Bedrock Converse error rate, Neptune CPU, OpenSearch search-rate.

## Full Architecture Diagram

```
                   ┌──────────────────────────┐
                   │  Browser                 │
                   │  retail-ontology.        │
                   │  <your-domain>           │
                   └────────────┬─────────────┘
                                │ HTTPS (ACM *.<your-domain>)
                                ▼
                   ┌──────────────────────────┐
                   │  CloudFront              │
                   │  + Lambda@Edge AuthFn    │◀──┐
                   │  + X-Origin-Auth-Token   │   │ 302 redirect
                   └────────────┬─────────────┘   │
                                │ HTTP origin     │
                                │ (CF SG-locked)  │
                                ▼                 │
                   ┌──────────────────────────┐   │
                   │  ALB (HTTP:80)           │   │
                   └─────┬─────────────┬──────┘   │
                         │             │          │
                  /api/* │             │ /*       │
                         ▼             ▼          │
              ┌──────────────┐  ┌──────────────┐  │
              │ API service  │  │ Web service  │  │
              │ FastAPI      │  │ Next.js 14   │  │
              │ Fargate ARM64│  │ Fargate ARM64│  │
              └──────┬───────┘  └──────────────┘  │
                     │                            │
       ┌─────────────┼──────────────┬─────────────┤
       │             │              │             │
       ▼             ▼              ▼             ▼
  ┌────────┐   ┌──────────┐   ┌────────────┐  ┌──────────┐
  │Neptune │   │OpenSearch│   │  Bedrock   │  │ Cognito  │
  │ Cypher │   │BM25 + KNN│   │ Sonnet 4.6 │  │ User Pool│
  └────────┘   └──────────┘   │ Embed/Rerank│ └──────────┘
                              │ Guardrails │
                              │ AgentCore  │
                              │ Memory + CI│
                              └────────────┘
```

## Data Flow Summary

User → CloudFront (auth) → ALB → API → (Neptune + OpenSearch + Bedrock + AgentCore Memory) → SSE stream → Web

## Infrastructure Tables

| Stack (CDK) | Resources |
|-------------|-----------|
| OntologyRetailNetwork | VPC, subnets (public/private), NAT, VPC endpoints |
| OntologyRetailData | Neptune cluster, OpenSearch collection, Aurora cluster, S3 buckets, KMS keys |
| OntologyRetailCompute | ECS cluster + services (api/web), ALB, ECR repos, IAM task roles |
| OntologyRetailAi | Bedrock guardrail, Knowledge Base, AgentCore Memory store |
| OntologyRetailEdge | CloudFront, Lambda@Edge auth function, Cognito user pool + client + domain |
| OntologyRetailObservability | CloudTrail, CloudWatch alarms, Cost Anomaly subscription |

## Key Design Decisions

- **Single image, two roles** — the API container ships with `data/load.py` and `scripts/` so the same image runs as either the API server or a one-shot loader via command override. Avoids a second ECR repo and second build pipeline.
- **SHA-pinned task definitions** — `:latest` mutability bites ECS deploys; we pin a SHA tag in each new task-definition revision so rollouts are deterministic.
- **Lambda@Edge stable-ID hardcoding** — Lambda@Edge cannot read SSM/Secrets, so user-pool/client IDs are baked at synth time. CDK outputs `UserPoolId` / `UserPoolClientId` / `UserPoolDomain` for drift detection. See [ADR-0003](decisions/0003-lambda-edge-stable-id-hardcode-strategy.md).
- **AgentCore Memory via AwsCustomResource** — four-layer-explicit pattern (SDK package + IAM prefix + API parameters + name regex). See [ADR-0001](decisions/0001-agentcore-memory-via-aws-custom-resource.md).
- **CloudTrail via L1 CfnTrail** — CDK 2.150 L2 `cloudtrail.Trail` emits empty `EventSelectors`. Workaround documented in [ADR-0002](decisions/0002-cloudtrail-via-cfntrail-with-manual-bucket-policy.md).
- **Cognito UserPoolClient CDK-only authoring** — `update-user-pool-client` has PUT semantics; drive every config change through `cdk deploy edge`. See [ADR-0004](decisions/0004-cognito-user-pool-client-cdk-driven.md).
- **Root-path Cognito gate + explicit logout endpoint** — `PUBLIC_PATHS` does NOT include `/`; anonymous viewers are 302'd to Cognito immediately rather than racing the SPA shell. `/api/auth/logout` clears all three token cookies and bounces to the Cognito Hosted UI logout. See [ADR-0012](decisions/0012-lambda-edge-root-gate-and-logout.md).
- **Sonnet 4.6 only** — chat and insights both use Sonnet 4.6 (env `BEDROCK_CHAT_MODEL_ID`). Haiku Lite was tested and rejected for analytical voice quality.

## Operations

- Per-resource AWS service deep dive: [docs/aws-resources.md](aws-resources.md)
- Smoke tests + verification commands: see [docs/onboarding.md](onboarding.md)
- Loader runs (Neptune + OpenSearch reload): see [docs/runbooks/](runbooks/)
- Auth domain changes: 4 surfaces must align — DNS, CF alias, Cognito callback, API `PUBLIC_DOMAIN` env. Lambda@Edge derives `redirect_uri` from request `Host` header so it adapts automatically to new aliases.
- Security trade-offs and production migration plan: [SECURITY.md](../SECURITY.md)

---

# 한국어

## 시스템 개요

`ontology-retail`은 한국 리테일/CPG 지식그래프를 위한 다층 AWS-네이티브 데모입니다. Fargate의 FastAPI 백엔드가 Bedrock + AgentCore + Neptune + OpenSearch를 앞단에서 묶고, Fargate의 Next.js 14 프런트엔드가 시나리오별 UI를 제공합니다. CloudFront + Lambda@Edge 쿠키 인증이 전체 표면을 감싸고 Cognito 사용자 풀이 접근을 통제합니다.

13개 wow 시나리오(A–M)는 의미 검색, 메모리 기반 대화형 에이전트, MD 인사이트, 페르소나 매칭, 안전성, 대체재, 가격·가용성, 물류 네트워크, 이탈 위험 진단, 확보 채널 ROI, 등급 상승 경로, 회원-거점 커버리지, **외부 소비 패널 × wallet-share 5축 VIP 타깃 빌더**에 걸쳐 있습니다. 온톨로지는 5개 계층(상거래/라이프스타일 Phase 1–2, 물류 Phase 5, 멤버쉽/마케팅 Phase 2A, 회원 지리 Phase 2A-G, **외부 소비 Phase 2B**)으로 구성되며, H/I/K/L 시나리오가 동일한 KOSTAT 17 시도 choropleth 지도를 공유합니다. 별도 `/codegraph` 메타 페이지는 graphify가 생성한 AST 그래프를 임베드하며, 159개 커뮤니티가 Bedrock Sonnet 4.6의 4-필드 JSON 출력(라벨·설명·핵심 개념·대표 파일)으로 오프라인 라벨링됩니다.

## 계층별 컴포넌트

### Edge & Auth

- **CloudFront 배포** (`<distribution-id>`) — TLS 종단, viewer/origin 캐싱, 커스텀 도메인 `retail-ontology.<your-domain>` + ACM `*.<your-domain>` 인증서 (`PUBLIC_DOMAIN`과 CloudFront alias로 지정. 최초 레퍼런스 배포는 `whchoi.net`을 사용했습니다).
- **Lambda@Edge** (`AuthEdgeFn`, us-east-1 `experimental.EdgeFunction`) — 모든 요청에 대해 쿠키 기반 인증 검사. `PUBLIC_PATHS` 화이트리스트(`callback`, `logout`, `_next`, `favicon`, `api/health`)는 의도적으로 좁게 — 루트 경로 `/`도 게이트되므로 미인증 viewer는 즉시 Cognito Hosted UI 302를 받고, half-loaded SPA 셸이 노출되지 않습니다. [ADR-0012](decisions/0012-lambda-edge-root-gate-and-logout.md) 참조.
- **Cognito User Pool** (`<user-pool-id>`) — RS256 JWT, OAuth code grant, 이메일=사용자명, 데모용 8자 비밀번호 정책. Hosted UI logout URL은 `https://<PUBLIC_DOMAIN>/`(슬래시 포함)을 등록해야 `/api/auth/logout`이 깨끗하게 착륙합니다.
- **Auth 라우터** (`api/routers/auth.py`) — `/api/auth/login`(사이드바 재인증), `/api/auth/callback`(OAuth code → 토큰 교환 + 쿠키 설정), `/api/auth/logout`(쿠키 삭제 + Cognito Hosted UI logout 302), `/api/auth/whoami`(항상 JSON 200, `{authenticated: bool, ...}`).
- **Origin Auth** — CloudFront가 Secrets Manager에 저장된 `X-Origin-Auth-Token` 헤더를 ALB로 전달, ALB SG는 `com.amazonaws.global.cloudfront.origin-facing`에 한정.

### Compute

- **Web 서비스** (ECS Fargate ARM64) — Next.js 14 standalone 빌드, ALB 뒤 2-복제.
- **API 서비스** (ECS Fargate ARM64) — FastAPI + uvicorn, 2-복제, 동일 이미지가 command override로 일회성 로더로도 동작.
- **ALB** (`ontology-retail-dev-alb`) — HTTP-80 origin (데모 단계에서는 CloudFront에서 TLS 종단; production 마이그레이션 계획은 SECURITY.md).

### Data & Search

- **Neptune 클러스터** (`ontology-retail-dev-neptune`) — 개발 사이즈 단일 인스턴스, openCypher 엔드포인트, SigV4 IAM 인증. 19개 노드 클래스(상거래 + 물류 + 이벤트), 약 5,000 노드 / 10,000 엣지가 ECS 일회성 로더로 적재됨.
- **OpenSearch Serverless 컬렉션** (`<opensearch-collection-id>`) — BM25용 Nori 한국어 분석기, Cohere `embed-v4` 1024차원 KNN, RRF 융합.
- **Aurora PostgreSQL Serverless v2** (`ontology-retail-dev-aurora`) — 세션 메타 + Cognito 연결.
- **S3 버킷** — `raw-docs` (KB 적재 소스), `uploads` (사용자 업로드), `synthetic-data` (로더 소스 — 상품/리뷰/페르소나 + regions/warehouses/carriers/routes/shipments/events/inventory), `ontology-snapshots` (버전 관리된 온톨로지).

### 물류 & 이벤트 (Phase 5)

- **Region / Warehouse / Carrier / Route / Shipment / Event / Inventory** — first-class 그래프 노드 + 엣지 `LOCATED_IN`, `OPERATES`, `FULFILLED_BY`, `FROM`/`TO`, `CARRIED_BY`, `VIA`, `CONTAINS`, `AFFECTS_REGION`, `AFFECTS_CATEGORY`, `HELD_AT`, `OF_SKU`.
- **한국 지도** — react-simple-maps + d3-geo, `web/public/korea-provinces.json` (KOSTAT 17 시도, 146 KB), 5:4 viewBox로 위도 ~36°N에서 한반도 비율 자연 유지.
- **Inventory 모델** — `Inventory`를 first-class 노드(`{wh_id, sku_id, on_hand_pallets, capacity_pallets, days_of_cover, temperature}`)로 둬서 그래프 워크 / 검증 / 시계열 확장 모두 자연스럽게. openCypher의 엣지 속성 제약을 우회.
- **물류 에이전트 도구** — `inventory_lookup`, `nearest_warehouses` (haversine k-NN), `shortest_path` (Route 엣지 위 BFS)를 `api/services/agent.py:TOOL_SPECS`에 등록 — 메인 채팅(B)과 `/logistics` 인라인 패널 양쪽에서 호출 가능.

### 멤버쉽 & 마케팅 (Phase 2A + Phase 2A-G)

- **Member / MembershipTier / Campaign / Transaction / Touchpoint** — 5-페르소나 spine 아래 5개 신규 노드 타입. 엣지: `BELONGS_TO`, `MATCHES_PERSONA`, `PREFERS_CHANNEL`, `MADE`, `OF_PRODUCT`, `HAS_TOUCHPOINT`, `FROM_CAMPAIGN`, `TARGETS`. 규모: 1,000 회원 · 4 등급 · 20 캠페인 · 7,862 거래 · 10,021 접점.
- **Persona spine + narrative 이중 구조** — 5 spine 페르소나 (`per_pregnant`, `per_kid_4yo_mom`, `per_camper`, `per_sensitive_skin`, `per_gluten_allergy`, `is_spine=true`)가 *세그먼트* 시나리오를 구동. 40 narrative `psn_*` 페르소나는 *persona-match* 시나리오를 구동. `(narrative)-[:DERIVED_FROM]->(spine)` 엣지 (10건, 적재 시 라벨 키워드 매칭) 가 두 모델을 연결 — UI에서 어떤 페르소나를 골라도 `MATCHES_PERSONA` ➝ spine ➝ Member 경로로 도달.
- **회원 지리 (Phase 2A-G)** — `(Member)-[:LIVES_IN]->(Region)`, KOSTAT 17 시도에 페르소나 편향 분포(camper×3.0 강원, kid_4yo_mom×2.0 경기 등). 물류 단에서 만들어진 `Region` 노드를 *재사용*하여 같은 코로플레스 뷰를 공유.
- **시나리오** — I (`/churn` + `/api/churn/*`) RFM 대시보드 + 지도 탭, J (`/acquisition` + `/api/acquisition/dashboard`) Campaign × Channel × Persona ROI 매트릭스, K (`/tier-up` + `/api/tier-up/*`) Silver→Gold lift + 지도 탭, L (`/coverage` + `/api/coverage/dashboard`) 회원-거점 커버리지 허브. 4개 모두 `MATCHES_PERSONA` 또는 DERIVED_FROM-bridge 1-hop 트래버설로 활성 페르소나 반영.

### 외부 소비 (Phase 2B — 시나리오 M / VIP)

- **IndustryCategory** — 10개 industry-level 노드. 8개는 GS1 brick `Category`에 `OVERLAPS_WITH` 엣지 (총 43건) 매핑, 2개는 의도적 *blind spot* (생활용품·캠핑 장비 — 우리 점유율 0%, Opportunity VIP 최강 신호).
- **(Member)-[:HAS_CATEGORY_SPEND {amount_krw, period}]->(IndustryCategory)** — 10,410 엣지 = Q1 2026 (5,205) + Q4 2025 (5,205). 페르소나 편향 분포 + 회원별 성장률(25% 강성장 / 35% 약성장 / 30% flat / 10% 하락)로 Trajectory VIP의 Q1/Q0 ratio 산출 가능.
- **5축 VIP 정의** — Opportunity / Loyal / Whale / Cross-category / Trajectory. 5개 모두 frontend에서 공통 `CandidatesTable<T>` + backend에서 공통 `_persona_filter_fragment()` 사용. ADR-0008 / 0009 참조.
- **시나리오 M 페이지** (`/vip` + `/api/vip/*`) — 5개 탭, 동일 OR 패턴으로 persona 인식, 단일 PersonaSwitch 토글로 5종 모두 탐색 가능.

### 코드 지식 그래프 (`/codegraph` — 메타)

- **graphify 정적 번들** — `web/public/codegraph/{graph.html, graph.json, manifest.json, GRAPH_REPORT.md}`. AST 전용 추출, 빌드 시 LLM 호출 0. 현재 스냅샷: 1,751 노드 / 2,217 엣지 / 159 커뮤니티 / 151 파일.
- **Bedrock Sonnet 4.6 커뮤니티 라벨링** — `scripts/label_codegraph_communities.py` 가 4-필드 JSON (label / description / key_concepts / top_files) 을 생성하여 `community_labels.json` + `community_meta.json` 작성. graph.html 의 `community_name: "Community NNN"` 1,751건을 in-place 패치하여 의미 라벨로 교체.
- **One-shot 갱신** — `scripts/refresh_codegraph.sh` 가 graphify update → bundle copy → Bedrock label → graph.html 패치 4단계를 ~3분에 자동 실행. 4단계는 `RAW_NODES[].community_name`(노드 툴팁)과 `LEGEND[].label`(우측 항상-노출 범례) **둘 다** 패치 — 한쪽만 패치하면 표면 간 불일치가 생깁니다. ADR-0010 + [ADR-0013](decisions/0013-codegraph-legend-label-patch.md) 참조.

### AI & Memory

- **Bedrock Sonnet 4.6** — 채팅·인사이트 (프로젝트 결정: Haiku Lite 사용 안 함).
- **Bedrock Cohere embed-v4** — 쿼리·문서 임베딩.
- **Bedrock Cohere rerank-v3** — cross-region inference profile, 실패 시 RRF 순위로 fallback.
- **Bedrock Knowledge Base** (`<knowledge-base-id>`) — `raw-docs` 위 매니지드 RAG 검색.
- **Bedrock Guardrails** (`<guardrail-id>`) — 채팅·인사이트 입출력 PII 스크럽.
- **AgentCore Memory** (`ontology_retail_dev_memory-<suffix>`) — short-term 세션 이벤트 + long-term 사용자별 사실, 7일 TTL.
- **AgentCore Code Interpreter** — matplotlib 차트 렌더링용 Firecracker microVM 래퍼(`api/services/code_interpreter.py`), 번들된 NanumGothic 폰트. **현재 어떤 라우터에도 연결되어 있지 않습니다** (`grep -rn code_interpreter api/routers/` 결과 없음). 시나리오 C는 대신 Neptune 집계에서 파생한 `chart_spec`을 반환하고 클라이언트에서 렌더링합니다. 연결 작업은 로드맵 항목으로 관리합니다.

### Observability & Safety

- **CloudTrail** — management 이벤트만 (Bedrock data 이벤트는 CloudTrail 이벤트 타입이 아님).
- **CloudWatch Logs** — `/aws/ecs/ontology-retail-dev/api`, `/aws/ecs/ontology-retail-dev/web`, AWS WAF 로그.
- **ALB Access Logs** — S3 보관, 30일 후 Glacier 라이프사이클.
- **Cost Anomaly Detection** — `Default-Services-Monitor` 구독, 이메일 알림.
- **계정 레벨 CloudWatch Alarms** — Bedrock Converse 에러율, Neptune CPU, OpenSearch search-rate.

## 전체 아키텍처 다이어그램

```
                   ┌──────────────────────────┐
                   │  브라우저                │
                   │  retail-ontology.        │
                   │  <your-domain>           │
                   └────────────┬─────────────┘
                                │ HTTPS (ACM *.<your-domain>)
                                ▼
                   ┌──────────────────────────┐
                   │  CloudFront              │
                   │  + Lambda@Edge AuthFn    │◀──┐
                   │  + X-Origin-Auth-Token   │   │ 302 리다이렉트
                   └────────────┬─────────────┘   │
                                │ HTTP origin     │
                                │ (CF SG 잠금)    │
                                ▼                 │
                   ┌──────────────────────────┐   │
                   │  ALB (HTTP:80)           │   │
                   └─────┬─────────────┬──────┘   │
                         │             │          │
                  /api/* │             │ /*       │
                         ▼             ▼          │
              ┌──────────────┐  ┌──────────────┐  │
              │ API 서비스   │  │ Web 서비스   │  │
              │ FastAPI      │  │ Next.js 14   │  │
              │ Fargate ARM64│  │ Fargate ARM64│  │
              └──────┬───────┘  └──────────────┘  │
                     │                            │
       ┌─────────────┼──────────────┬─────────────┤
       │             │              │             │
       ▼             ▼              ▼             ▼
  ┌────────┐   ┌──────────┐   ┌────────────┐  ┌──────────┐
  │Neptune │   │OpenSearch│   │  Bedrock   │  │ Cognito  │
  │ Cypher │   │BM25 + KNN│   │ Sonnet 4.6 │  │User Pool │
  └────────┘   └──────────┘   │Embed/Rerank│  └──────────┘
                              │ Guardrails │
                              │ AgentCore  │
                              │ Memory + CI│
                              └────────────┘
```

## 데이터 플로우 요약

사용자 → CloudFront (인증) → ALB → API → (Neptune + OpenSearch + Bedrock + AgentCore Memory) → SSE 스트림 → Web

## 인프라 테이블

| 스택 (CDK) | 리소스 |
|------------|--------|
| OntologyRetailNetwork | VPC, 서브넷(public/private), NAT, VPC 엔드포인트 |
| OntologyRetailData | Neptune 클러스터, OpenSearch 컬렉션, Aurora 클러스터, S3 버킷, KMS 키 |
| OntologyRetailCompute | ECS 클러스터 + 서비스(api/web), ALB, ECR 리포, IAM 태스크 롤 |
| OntologyRetailAi | Bedrock guardrail, Knowledge Base, AgentCore Memory store |
| OntologyRetailEdge | CloudFront, Lambda@Edge 인증 함수, Cognito 사용자 풀 + 클라이언트 + 도메인 |
| OntologyRetailObservability | CloudTrail, CloudWatch 알람, Cost Anomaly 구독 |

## 핵심 설계 결정

- **단일 이미지, 두 가지 역할** — API 컨테이너가 `data/load.py`와 `scripts/`를 함께 번들하기 때문에 동일 이미지가 command override로 API 서버 또는 일회성 로더로 모두 작동합니다. 두 번째 ECR 리포 + 두 번째 빌드 파이프라인을 피합니다. ([ADR pending](decisions/0001-single-image-two-roles.md))
- **SHA-pinned 태스크 정의** — `:latest` mutability가 ECS 배포에서 문제를 일으키므로 새 태스크 정의 revision마다 SHA 태그를 명시 — 결정적 롤아웃.
- **하드코딩된 Cognito ID를 가진 Lambda@Edge inline 코드** — Lambda@Edge는 SSM/Secrets에 접근할 수 없어 사용자 풀/클라이언트 ID를 synth 시점에 baked in. CDK가 `UserPoolId` / `UserPoolClientId` / `UserPoolDomain`을 drift 감지용으로 출력합니다 (ADR-0003 참조).
- **AgentCore Memory CDK gotchas** — AwsCustomResource v3 explicit form + fromStatements + underscore-only names 사용 (`agentcore_gotchas.md`에 기록).
- **Sonnet 4.6만 사용** — 채팅·인사이트 모두 Sonnet 4.6 (env `BEDROCK_CHAT_MODEL_ID`). Haiku Lite는 분석 어조 품질 문제로 기각.
- **루트 경로 Cognito 게이트 + 명시적 logout 엔드포인트** — `PUBLIC_PATHS`에 `/`가 포함되지 않아 미인증 viewer는 SPA 셸을 받지 않고 즉시 Cognito 302를 받습니다. `/api/auth/logout`이 3종 토큰 쿠키를 모두 지우고 Cognito Hosted UI 로그아웃으로 바운스. [ADR-0012](decisions/0012-lambda-edge-root-gate-and-logout.md) 참조.

> `docs/decisions/`에 ADR-0001 ~ 0013까지 13개의 결정이 Context/Decision/Alternatives/Consequences 형식으로 정리되어 있습니다 — Bedrock·AgentCore·CloudTrail·Lambda@Edge·Cognito·페르소나 spine·멤버십·VIP·codegraph·사이드바 로고 등 영역별로 묶여 있습니다.

## 운영

- 자원별 AWS 서비스 상세: [docs/aws-resources.md](aws-resources.md)
- 스모크 테스트 + 검증 명령어: [docs/onboarding.md](onboarding.md)
- 로더 실행 (Neptune + OpenSearch 재적재): [docs/runbooks/](runbooks/)
- 인증 도메인 변경: 4개 surface 정렬 필요 — DNS, CF alias, Cognito callback, API `PUBLIC_DOMAIN` env. Lambda@Edge는 request `Host` 헤더로 `redirect_uri`를 유도하므로 새 alias에 자동으로 적응합니다.
- 보안 트레이드오프 및 production 마이그레이션 계획: [SECURITY.md](../SECURITY.md)
