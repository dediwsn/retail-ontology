# ontology-retail

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![English](https://img.shields.io/badge/lang-English-blue.svg)](#english)
[![한국어](https://img.shields.io/badge/lang-한국어-red.svg)](#한국어)

A 30–60 minute proof-of-concept demo for a Korean Retail/CPG knowledge graph on AWS Bedrock + AgentCore + Neptune (13 wow scenarios + meta `/codegraph`).

AWS Bedrock + AgentCore + Neptune 위에서 한국 리테일/CPG 지식그래프 13개 wow 시나리오 + 메타 `/codegraph` 페이지를 보여주는 30–60분 PoC 데모.

---

# English

## Overview

`ontology-retail` is a hands-on demonstration of how a domain ontology (products, ingredients, personas, channels, trends, reviews, members, regions, **industry categories**) can power **thirteen distinct retail-experience scenarios (A–M)** on AWS managed AI services. The demo deploys a multi-tier application — FastAPI backend, Next.js 14 frontend, AWS CDK infrastructure — that integrates Bedrock Sonnet 4.6, AgentCore Memory, Neptune openCypher, OpenSearch Serverless hybrid search, and CloudFront-fronted ECS Fargate. An AgentCore Code Interpreter wrapper (`api/services/code_interpreter.py`) is implemented but not yet wired into a route.

The scenarios span semantic search, conversational agents with multi-turn memory, MD-grade analytics with streaming token summaries, persona matching, safety-lens filtering, substitution recommendations, channel-aware price/availability comparison, logistics network mapping, churn-risk diagnosis, acquisition-channel ROI, tier-up path lift analysis, member-warehouse coverage mapping, and **wallet-share-aware VIP target building with 5 strategic axes** (Opportunity / Loyal / Whale / Cross-category / Trajectory). A separate `/codegraph` meta page embeds a graphify-generated AST graph of the codebase itself, with 159 communities labelled offline via Bedrock Sonnet.

## Demo

[![Watch the demo on YouTube](https://img.youtube.com/vi/irGMb3x6Iys/maxresdefault.jpg)](https://youtu.be/irGMb3x6Iys)

Walkthrough of all 13 wow scenarios (A–M) and the `/codegraph` meta page. Click the thumbnail to watch on YouTube.

## Features

- **Semantic Search (A)** — Korean natural-language queries through OpenSearch BM25 (Nori) + Cohere KNN hybrid, fused with reciprocal-rank fusion, then reranked with `cohere.rerank-v3` and visualized as a 1-hop knowledge subgraph.
- **Conversational Agent (B)** — Bedrock Converse multi-turn with AgentCore Memory short/long-term recall and four tool definitions (memory_recall, neptune_subgraph, semantic_search, kb_lookup), streamed via SSE with a live tool-call panel.
- **MD Insights (C)** — Neptune Trend↔Ingredient aggregation runs first, then Sonnet 4.6 streams a Korean summary over those rows (the system prompt forbids inventing figures absent from the data). The endpoint returns a `chart_spec` (`{type, title, data[]}`) computed from the same aggregation, which the client renders — so charted values come from the graph, not the model. A deterministic recap is emitted if Bedrock is unavailable. *`api/services/code_interpreter.py` (AgentCore Code Interpreter + matplotlib + NanumGothic) is implemented but no router imports it, so no server-side PNG is produced on this path.*
- **Persona Match (D)** — Forty synthetic personas across HAS_CONCERN graph traversal with weighted SKU recommendations.
- **Safety Lens (E)** — Bedrock Guardrails plus KFDA/INCI ingredient blacklists for pregnancy, pediatric, and allergen filtering.
- **Substitute Finder (F)** — Same-category, cross-brand substitution traversal with price-delta cards.
- **Price/Availability Compare (G)** — Four-channel (CU, eMart, Olive Young, Kurly) price/discount/stock matrix with persona-channel affinity weighting.
- **Logistics Network (H)** — Korean choropleth map with 30 warehouses, 76 lanes, 940 inventory rows, KPI strip (OTD rate, active shipments, transit time, exceptions, active events), and an inline LLM panel for natural-language queries (`inventory_lookup`, `nearest_warehouses` haversine k-NN, `shortest_path` BFS).
- **Churn Risk (I)** — RFM-based `churn_risk` per Member with tier × persona breakdowns, Top-30 at-risk drilldown with 1-hop graph, persona-aware winback recommendation, and a 17-sido choropleth map tab keyed on average churn risk.
- **Acquisition ROI (J)** — Per-campaign and per-channel ROI rollup (cost ÷ attributed LTV from responded touchpoints), plus a Persona × Channel response-rate heatmap (best channel per persona archetype).
- **Tier-up Path (K)** — Silver→Gold lift on products and categories (per-capita Gold-rate ÷ Silver-rate with Laplace smoothing), upgrade-candidate ranking (Silver with LTV ≥ 1.5M sorted by gap-to-Gold), plus a 17-sido map tab keyed on candidate density.
- **Coverage Map (L)** — Persona-filtered choropleth of member distribution by 시도 + Warehouse markers + 4-dimension toggle (count / avg churn / avg LTV / uncovered share) + radius slider. Single KPI "회원 중 N km 안에 거점 없는 비율" — the hub scenario that bridges membership · logistics · persona on one screen.
- **VIP Target Builder (M)** — Phase 2B external consumption panel (10 IndustryCategory × 10,410 quarterly spend edges across Q1+Q4) layered above internal Transactions through the OVERLAPS_WITH bridge. Five wallet-share-aware VIP definitions on one screen — Opportunity (low share / high total) · Loyal (share≥0.5 majority defenders) · Whale (tier=VIP & LTV≥5M) · Cross-category (single-internal-cat buyer + big external in non-overlapping industry) · Trajectory (Q1/Q0 growth ≥1.2 + tier≠VIP "future VIPs"). Indigo color identity.
- **Code Knowledge Graph (`/codegraph`, meta)** — graphify-generated AST graph (1,751 nodes / 2,217 edges / 159 communities / 151 source files), no LLM at build time. Communities are labelled offline via Bedrock Sonnet 4.6 returning 4-field JSON (label / description / key_concepts / top_files); graph.html is patched in-place to show semantic Korean community names. Refresh via `./scripts/refresh_codegraph.sh`.
- **Sidebar Company Logo** — Configurable company logo at sidebar top (default AWS), click-cycles through 4 bundled SVG presets and persists in localStorage. Default preset overridable at build time via `NEXT_PUBLIC_DEFAULT_LOGO_PRESET=<id>`. See `web/public/logos/README.md` for adding a custom brand SVG.
- **Knowledge Graph Explorer** — Per-type browsers for products, ingredients, concerns, trends, brands, categories, personas, channels, manufacturers, reviews, regions, warehouses, carriers, events, members, tiers, campaigns, transactions, touchpoints, and **industry categories**.
- **Ontology Meta** — Cytoscape ER diagram, standards mapping CSV browser, and validation coverage report (INCI/FoodOn/GS1+KFDA/Loader).
- **Operations Console** — Ingest counts, guardrail logs, AgentCore memory snapshots, eval pass-rate scoreboard, and tool-call trace timeline.

## Prerequisites

- AWS account with Bedrock, Neptune, OpenSearch Serverless, and AgentCore enabled in `ap-northeast-2`
- AWS CLI v2 with credentials (SSO or IAM)
- Node.js 20 or later
- Python 3.12 or later
- Docker with `linux/arm64` build support (Graviton ECS targets)
- AWS CDK v2.150 or later

## Installation

```bash
# Clone the repository
git clone https://github.com/whchoi98/ontology-retail.git
cd ontology-retail

# Install backend dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

# Install frontend dependencies
cd web && npm ci && cd -

# Install infrastructure dependencies
cd infra-cdk && npm ci && cd -

# Bootstrap CDK and deploy stacks
cd infra-cdk
npx cdk bootstrap aws://<account>/ap-northeast-2
npx cdk deploy --all
```

## Usage

```bash
# Build and push API + Web container images to ECR
docker build --platform linux/arm64 -f api/Dockerfile -t <ecr>/ontology-retail-dev-api:latest .
docker build --platform linux/arm64 -f web/Dockerfile -t <ecr>/ontology-retail-dev-web:latest .
docker push <ecr>/ontology-retail-dev-api:latest
docker push <ecr>/ontology-retail-dev-web:latest

# Reload synthetic data into Neptune + OpenSearch (one-shot ECS task)
aws ecs run-task \
  --cluster ontology-retail-dev-cluster \
  --task-definition ontology-retail-dev-api \
  --launch-type FARGATE \
  --overrides file://loader-overrides.json
# Loads ~250 products, 2,480 reviews, 40 personas, 4 channels, 219 FoodOn aliases

# Force a service rollout after image push
aws ecs update-service \
  --cluster ontology-retail-dev-cluster \
  --service ontology-retail-dev-api \
  --force-new-deployment

# Visit the deployed CloudFront domain
open https://<cloudfront-distribution>.cloudfront.net
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region for all services | `ap-northeast-2` |
| `NEPTUNE_ENDPOINT` | Neptune cluster writer endpoint | resolved from CDK output |
| `OPENSEARCH_ENDPOINT` | OpenSearch Serverless collection endpoint | resolved from CDK output |
| `OPENSEARCH_INDEX` | Vector + BM25 index name | `ontology-retail-dev-kb-index` |
| `BEDROCK_CHAT_MODEL_ID` | Foundation model for chat and insights | `global.anthropic.claude-sonnet-4-6` |
| `BEDROCK_KB_ID` | Bedrock Knowledge Base ID | resolved from CDK output |
| `BEDROCK_GUARDRAIL_ID` | Bedrock Guardrails ID | resolved from CDK output |
| `BEDROCK_RERANKER_INFERENCE_PROFILE_ARN` | Cross-region inference profile for reranker | (set per environment) |
| `BEDROCK_EMBED_MODEL_ID` | Embedding model | `global.cohere.embed-v4:0` |
| `AGENTCORE_MEMORY_ID` | AgentCore Memory store ID | resolved from CDK output |
| `COGNITO_USER_POOL_ID` | Cognito user pool for SSO | resolved from CDK output |
| `ORIGIN_AUTH_SECRET_ARN` | CloudFront-to-ALB shared secret ARN | resolved from CDK output |
| `RAW_DOCS_BUCKET` | S3 bucket for KB raw documents | `ontology-retail-dev-raw-docs-<account>` |
| `UPLOADS_BUCKET` | S3 bucket for user uploads | `ontology-retail-dev-uploads-<account>` |
| `SYNTHETIC_DATA_BUCKET` | S3 bucket for loader sync | `ontology-retail-dev-synthetic-data-<account>` |
| `ONTOLOGY_ENV` | Environment name | `dev` |
| `PUBLIC_DOMAIN` | CloudFront distribution domain | resolved from CDK output |

## Project Structure

```
ontology-retail/
├── api/                  # FastAPI backend (Python 3.12, ARM64)
│   ├── routers/          # Per-scenario endpoints (chat, search, insights, logistics, ...)
│   ├── services/         # Bedrock, Neptune, OpenSearch, AgentCore wrappers
│   ├── middleware_auth.py # Cognito JWT verification
│   └── Dockerfile        # Multi-purpose: API server + one-shot data loader
├── web/                  # Next.js 14 frontend (TypeScript, ARM64)
│   ├── app/              # App Router scenarios A-M + objects + ops + meta + /codegraph
│   ├── components/       # PersonaSwitch, GuidedTour, CytoscapeView, Sidebar
│   └── lib/api-client.ts # Typed SSE + REST client
├── infra-cdk/            # AWS CDK v2 infrastructure (TypeScript)
│   ├── lib/              # network, data, compute, ai, edge, observability stacks
│   └── test/             # Jest snapshot tests for all 6 stacks
├── data/                 # Synthetic data generator + Neptune/OpenSearch loader
├── ontology/             # Mapping CSVs (INCI, FoodOn, GS1↔KFDA)
├── tests/                # Pytest suite — smoke + tests/api/ (httpx integration)
├── docs/                 # Architecture, ADRs (decisions/0001-0004), runbooks
├── scripts/              # KB index, Cognito provisioning, evaluation
├── .claude/              # Project harness — agents, skills, hooks, commands
├── .github/workflows/    # CI pipeline (python-ast, tsc, cdk-synth+jest, pytest)
└── .harness-eval/        # Score history (drives the Harness Score badge)
```

## Testing

The project has four test surfaces, ordered fastest first:

```bash
# 1. Python AST validation (no installs, ~1s) — also a CI job
python3 -m compileall -q api data scripts

# 2. TypeScript type-check (~10s with cache) — runs for both web and infra-cdk in CI
cd web && npx tsc --noEmit
cd infra-cdk && npx tsc --noEmit

# 3. Pytest offline suite (28 tests, <1s) — smoke imports + Pydantic validation + /api/search integration with mocked services
pip install -r api/requirements.txt -r requirements-dev.txt
pytest tests -q

# 4. CDK snapshot tests (6 stacks, ~13s) — drift detection on Template.fromStack().toJSON()
cd infra-cdk && npx jest --ci

# 5. Live wow-query evaluation against deployed CloudFront (target ≥85%, sys.exit(1) below)
python3 scripts/eval_wow_queries.py
```

Steps 1–4 run in `.github/workflows/ci.yml` on every push/PR (concurrency cancel-in-progress). Step 5 requires a deployed environment.

## API Documentation

See [docs/api-reference.md](docs/api-reference.md) for the full OpenAPI surface, including:

- `POST /api/search` and `POST /api/search/stream` (Scenario A)
- `POST /api/chat` (Scenario B, SSE)
- `POST /api/insights` and `POST /api/insights/stream` (Scenario C)
- `POST /api/persona-match` (Scenario D)
- `POST /api/safety/check` (Scenario E)
- `POST /api/substitute` (Scenario F)
- `POST /api/price/compare` (Scenario G)
- `GET  /api/logistics/{network,status,events,warehouse/...,inventory/...,nearest,shortest-path}` (Scenario H)
- `GET  /api/objects/{type}` and `/api/objects/{type}/{id}`
- `GET  /api/ontology/{schema,standards,validation}`
- `GET  /api/ops/{ingest,guardrail,memory,eval,trace}`

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feat/<scenario-or-fix>`.
3. Make changes following the conventions in [CLAUDE.md](CLAUDE.md). Use Conventional Commits format (e.g. `feat(api): add price compare`, `fix(infra-cdk): correct Cognito password policy`).
4. Push the branch: `git push origin feat/<scenario-or-fix>`.
5. Open a Pull Request describing the scenario impact and any infrastructure changes.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Contact

- Maintainer: [whchoi98](https://github.com/whchoi98)
- Issues: <https://github.com/whchoi98/ontology-retail/issues>
- Email: whchoi98@gmail.com

---

# 한국어

## 개요

`ontology-retail`은 한국 리테일/CPG 도메인 온톨로지(상품, 성분, 페르소나, 채널, 트렌드, 리뷰, 회원, 지역, **산업 카테고리**)가 AWS 매니지드 AI 서비스 위에서 **열세 가지 리테일 경험 시나리오 (A–M)** 를 어떻게 구동하는지 보여주는 PoC 데모입니다. FastAPI 백엔드, Next.js 14 프론트엔드, AWS CDK 인프라로 구성된 다층 애플리케이션이 Bedrock Sonnet 4.6, AgentCore Memory, Neptune openCypher, OpenSearch Serverless 하이브리드 검색, CloudFront 앞단에 ECS Fargate를 통합합니다. AgentCore Code Interpreter 래퍼(`api/services/code_interpreter.py`)는 구현되어 있으나 아직 라우터에 연결되지 않았습니다.

시나리오는 의미 검색, 다회차 메모리 기반 대화형 에이전트, 토큰 스트리밍 요약을 갖춘 MD급 분석, 페르소나 매칭, 안전성 렌즈 필터링, 대체재 추천, 채널 인지 가격·가용성 비교, 한국 지도 기반 물류 네트워크, 이탈 위험 진단, 확보 채널 ROI, 등급 상승 경로, 회원-거점 커버리지, **외부 소비 패널 × wallet-share 5축 VIP 타깃 빌더**(Opportunity / Loyal / Whale / Cross-category / Trajectory)에 걸쳐 있습니다. 별도 `/codegraph` 메타 페이지는 graphify가 생성한 코드베이스의 AST 그래프(159개 커뮤니티가 Bedrock Sonnet으로 자동 라벨링)를 임베드합니다.

## 데모 영상

[![YouTube에서 데모 보기](https://img.youtube.com/vi/irGMb3x6Iys/maxresdefault.jpg)](https://youtu.be/irGMb3x6Iys)

13개 wow 시나리오(A–M)와 `/codegraph` 메타 페이지의 워크쓰루. 썸네일을 클릭하면 YouTube로 이동합니다.

## 주요 기능

- **의미 검색 (A)** — 한국어 자연어 쿼리를 OpenSearch BM25(Nori) + Cohere KNN 하이브리드로 처리하고 RRF로 융합한 뒤 `cohere.rerank-v3`으로 재정렬해 1-hop 지식그래프 부분그래프와 함께 시각화합니다.
- **대화형 에이전트 (B)** — Bedrock Converse 다회차 + AgentCore Memory short/long-term 회상 + 4개 도구 정의(memory_recall, neptune_subgraph, semantic_search, kb_lookup)를 SSE로 스트리밍하며 실시간 도구 호출 패널을 보여줍니다.
- **MD 인사이트 (C)** — Neptune Trend↔Ingredient 집계가 **먼저** 실행되고, 그 결과 위에서 Sonnet 4.6이 한국어 요약을 토큰 단위로 스트리밍합니다(시스템 프롬프트가 데이터에 없는 수치 생성을 금지). 엔드포인트는 같은 집계에서 계산한 `chart_spec`(`{type, title, data[]}`)을 반환하고 클라이언트가 렌더링하므로, 차트 값은 모델이 아니라 그래프에서 나옵니다. Bedrock 장애 시에는 동일한 집계로 만든 결정론적 요약이 대신 나갑니다. *`api/services/code_interpreter.py`(AgentCore Code Interpreter + matplotlib + NanumGothic)는 구현되어 있으나 어떤 라우터도 import하지 않아, 이 경로에서 서버측 PNG는 생성되지 않습니다.*
- **페르소나 매칭 (D)** — 40개 합성 페르소나를 대상으로 HAS_CONCERN 그래프 워크 + 가중 SKU 추천을 산출합니다.
- **안전성 렌즈 (E)** — Bedrock Guardrails + KFDA/INCI 성분 블랙리스트 기반 임산부/영유아/알러젠 필터링.
- **대체재 추천 (F)** — 동일 카테고리·다른 브랜드 대체재 워크 + 가격 차이 카드.
- **가격·가용성 비교 (G)** — 4채널(CU, 이마트, 올리브영, 마컬) 가격/할인/재고 매트릭스에 페르소나-채널 친화도 가중치를 적용합니다.
- **물류 네트워크 (H)** — 한국 시도 choropleth 지도에 30 거점 + 76 lane + 940 재고 row, KPI 스트립(OTD 준수율 / 활성 출하 / 평균 transit / 예외 / 활성 이벤트), 자연어 질의용 인라인 LLM 패널(`inventory_lookup`, `nearest_warehouses` haversine k-NN, `shortest_path` BFS).
- **이탈 위험 진단 (I)** — 회원별 RFM 기반 `churn_risk` + 등급·페르소나별 분포 + 상위 30명 드릴다운(1-hop 그래프) + 페르소나 맞춤 winback 추천 + 17 시도 평균 이탈 위험 코로플레스 *지도 탭*.
- **확보 채널 ROI (J)** — 캠페인별·채널별 ROI 롤업(비용 ÷ 응답 touchpoint 귀속 LTV) + Persona × Channel 응답률 히트맵.
- **등급 상승 경로 (K)** — 상품·카테고리별 Silver→Gold lift(per-capita Laplace smoothing), LTV ≥ 1.5M Silver 회원 업그레이드 후보 + 17 시도 후보 밀도 *지도 탭*.
- **회원-거점 커버리지 (L)** — 페르소나 컨텍스트로 필터링된 회원의 시도별 분포 코로플레스 + Warehouse 마커 + 4 차원 토글 + radius 슬라이더. KPI 하나 — "회원 중 N km 안에 거점 없는 비율" — 으로 멤버쉽·물류·페르소나를 한 화면에서 직조하는 *허브* 시나리오.
- **VIP 타깃 빌더 (M)** — Phase 2B 외부 소비 패널 (10 IndustryCategory × 10,410 분기별 지출 엣지, Q1+Q4) 을 내부 Transaction 위에 OVERLAPS_WITH 브릿지로 join. 한 화면에서 5종 wallet-share VIP 정의 — Opportunity (저점유·고총액) · Loyal (점유율≥0.5 방어) · Whale (tier=VIP & LTV≥5M) · Cross-category (단일 내부 카테고리 + 인접 외부 큰 지출) · Trajectory (Q1/Q0 성장률≥1.2 + tier≠VIP, 잠재 VIP). Indigo 색.
- **코드 지식 그래프 (`/codegraph`, 메타)** — graphify가 생성한 코드베이스 AST 그래프 (1,751 노드 / 2,217 엣지 / 159 커뮤니티 / 151 파일), 빌드 시 LLM 호출 0. 커뮤니티는 Bedrock Sonnet 4.6의 4-필드 JSON (라벨 / 설명 / 핵심 개념 / 대표 파일)으로 오프라인 라벨링. graph.html을 in-place 패치하여 의미 있는 한국어 라벨로 표시. 갱신은 `./scripts/refresh_codegraph.sh`.
- **사이드바 회사 로고** — 사이드바 상단에 설정 가능 회사 로고(기본 AWS), 클릭으로 4개 번들 SVG 프리셋 순환 + localStorage 영속화. 빌드 시 기본값을 `NEXT_PUBLIC_DEFAULT_LOGO_PRESET=<id>` 로 override 가능. 커스텀 브랜드 SVG 추가는 `web/public/logos/README.md` 참조.
- **지식그래프 객체 탐색** — 상품, 성분, 관심사, 트렌드, 브랜드, 카테고리, 페르소나, 채널, 제조사, 리뷰, 지역, 거점, 운송사, 이벤트, 회원, 등급, 캠페인, 거래, 접점, **산업 카테고리** 별 탐색기.
- **온톨로지 메타** — Cytoscape ER 다이어그램, 표준 매핑 CSV 브라우저, 검증 커버리지 리포트(INCI/FoodOn/GS1+KFDA/Loader).
- **운영 콘솔** — 적재 카운트, 가드레일 로그, AgentCore 메모리 스냅샷, 평가 pass-rate 스코어보드, 도구 호출 트레이스 타임라인.

## 사전 요구 사항

- `ap-northeast-2`에서 Bedrock, Neptune, OpenSearch Serverless, AgentCore가 활성화된 AWS 계정
- 자격 증명이 구성된 AWS CLI v2 (SSO 또는 IAM)
- Node.js 20 이상
- Python 3.12 이상
- `linux/arm64` 빌드를 지원하는 Docker (Graviton ECS 타깃)
- AWS CDK v2.150 이상

## 설치 방법

```bash
# 저장소 클론
git clone https://github.com/whchoi98/ontology-retail.git
cd ontology-retail

# 백엔드 의존성 설치
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

# 프론트엔드 의존성 설치
cd web && npm ci && cd -

# 인프라 의존성 설치
cd infra-cdk && npm ci && cd -

# CDK 부트스트랩 + 전체 스택 배포
cd infra-cdk
npx cdk bootstrap aws://<account>/ap-northeast-2
npx cdk deploy --all
```

## 사용법

```bash
# API + Web 컨테이너 이미지 빌드 후 ECR로 푸시
docker build --platform linux/arm64 -f api/Dockerfile -t <ecr>/ontology-retail-dev-api:latest .
docker build --platform linux/arm64 -f web/Dockerfile -t <ecr>/ontology-retail-dev-web:latest .
docker push <ecr>/ontology-retail-dev-api:latest
docker push <ecr>/ontology-retail-dev-web:latest

# 합성 데이터를 Neptune + OpenSearch로 일회성 ECS 태스크로 적재
aws ecs run-task \
  --cluster ontology-retail-dev-cluster \
  --task-definition ontology-retail-dev-api \
  --launch-type FARGATE \
  --overrides file://loader-overrides.json
# 약 250개 상품, 2,480개 리뷰, 40명 페르소나, 4개 채널, 219개 FoodOn 한글 매핑 적재

# 이미지 푸시 후 서비스 강제 롤아웃
aws ecs update-service \
  --cluster ontology-retail-dev-cluster \
  --service ontology-retail-dev-api \
  --force-new-deployment

# 배포된 CloudFront 도메인 접속
open https://<cloudfront-distribution>.cloudfront.net
```

## 환경 설정

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `AWS_REGION` | 모든 서비스가 배포되는 AWS 리전 | `ap-northeast-2` |
| `NEPTUNE_ENDPOINT` | Neptune 클러스터 writer 엔드포인트 | CDK output에서 자동 해석 |
| `OPENSEARCH_ENDPOINT` | OpenSearch Serverless 컬렉션 엔드포인트 | CDK output에서 자동 해석 |
| `OPENSEARCH_INDEX` | 벡터 + BM25 인덱스 이름 | `ontology-retail-dev-kb-index` |
| `BEDROCK_CHAT_MODEL_ID` | 채팅·인사이트용 Foundation 모델 | `global.anthropic.claude-sonnet-4-6` |
| `BEDROCK_KB_ID` | Bedrock Knowledge Base ID | resolved from CDK output |
| `BEDROCK_GUARDRAIL_ID` | Bedrock Guardrails ID | resolved from CDK output |
| `BEDROCK_RERANKER_INFERENCE_PROFILE_ARN` | 리랭커 cross-region inference profile | 환경별 설정 |
| `BEDROCK_EMBED_MODEL_ID` | 임베딩 모델 | `global.cohere.embed-v4:0` |
| `AGENTCORE_MEMORY_ID` | AgentCore Memory store ID | CDK output에서 자동 해석 |
| `COGNITO_USER_POOL_ID` | SSO용 Cognito 사용자 풀 | CDK output에서 자동 해석 |
| `ORIGIN_AUTH_SECRET_ARN` | CloudFront ↔ ALB 공유 비밀 ARN | CDK output에서 자동 해석 |
| `RAW_DOCS_BUCKET` | KB 원본 문서 S3 버킷 | `ontology-retail-dev-raw-docs-<account>` |
| `UPLOADS_BUCKET` | 사용자 업로드 S3 버킷 | `ontology-retail-dev-uploads-<account>` |
| `SYNTHETIC_DATA_BUCKET` | 로더 동기화용 S3 버킷 | `ontology-retail-dev-synthetic-data-<account>` |
| `ONTOLOGY_ENV` | 환경 이름 | `dev` |
| `PUBLIC_DOMAIN` | CloudFront 배포 도메인 | CDK output에서 자동 해석 |

## 프로젝트 구조

```
ontology-retail/
├── api/                  # FastAPI 백엔드 (Python 3.12, ARM64)
│   ├── routers/          # 시나리오별 엔드포인트 (chat, search, insights, ...)
│   ├── services/         # Bedrock, Neptune, OpenSearch, AgentCore 래퍼
│   ├── middleware_auth.py # Cognito JWT 검증
│   └── Dockerfile        # 다목적 이미지 — API 서버 + 일회성 데이터 로더
├── web/                  # Next.js 14 프론트엔드 (TypeScript, ARM64)
│   ├── app/              # App Router 시나리오 A-G + 객체 + 운영 + 메타
│   ├── components/       # PersonaSwitch, GuidedTour, CytoscapeView, Sidebar
│   └── lib/api-client.ts # 타입 안전 SSE + REST 클라이언트
├── infra-cdk/            # AWS CDK v2 인프라 (TypeScript)
│   └── lib/              # network, data, compute, ai, edge, observability 스택
├── data/                 # 합성 데이터 생성기 + Neptune/OpenSearch 로더
├── ontology/             # 매핑 CSV (INCI, FoodOn, GS1↔KFDA)
├── docs/                 # 아키텍처, ADR, 런북
└── scripts/              # KB 인덱스, Cognito 사용자 프로비저닝, 평가
```

## 테스트

빠른 순서대로 5개 테스트 surface:

```bash
# 1. Python AST 검증 (설치 불필요, ~1초) — CI job 1
python3 -m compileall -q api data scripts

# 2. TypeScript 타입 검사 (캐시 시 ~10초) — CI는 web + infra-cdk 매트릭스로 실행
cd web && npx tsc --noEmit
cd infra-cdk && npx tsc --noEmit

# 3. Pytest 오프라인 스위트 (28 tests, <1초) — smoke import + Pydantic 검증 + /api/search 통합 (서비스 모킹)
pip install -r api/requirements.txt -r requirements-dev.txt
pytest tests -q

# 4. CDK 스냅샷 테스트 (6 stacks, ~13초) — Template.fromStack().toJSON() drift 감지
cd infra-cdk && npx jest --ci

# 5. 배포된 CloudFront 대상 wow 쿼리 라이브 평가 (목표 ≥85%, 미달 시 sys.exit(1))
python3 scripts/eval_wow_queries.py
```

1–4 단계는 `.github/workflows/ci.yml`이 push/PR마다 실행 (concurrency cancel-in-progress). 5 단계는 배포된 환경 필요.

## API 문서

전체 OpenAPI 표면은 [docs/api-reference.md](docs/api-reference.md)에 정리돼 있습니다. 포함되는 엔드포인트:

- `POST /api/search` 및 `POST /api/search/stream` (시나리오 A)
- `POST /api/chat` (시나리오 B, SSE)
- `POST /api/insights` 및 `POST /api/insights/stream` (시나리오 C)
- `POST /api/persona-match` (시나리오 D)
- `POST /api/safety/check` (시나리오 E)
- `POST /api/substitute` (시나리오 F)
- `POST /api/price/compare` (시나리오 G)
- `GET  /api/logistics/{network,status,events,warehouse/...,inventory/...,nearest,shortest-path}` (시나리오 H)
- `GET  /api/objects/{type}` 및 `/api/objects/{type}/{id}`
- `GET  /api/ontology/{schema,standards,validation}`
- `GET  /api/ops/{ingest,guardrail,memory,eval,trace}`

## 기여 방법

1. 저장소를 Fork 합니다.
2. 기능 브랜치를 생성합니다: `git checkout -b feat/<scenario-or-fix>`.
3. [CLAUDE.md](CLAUDE.md)의 컨벤션에 따라 변경합니다. 커밋 메시지는 Conventional Commits 형식을 사용합니다 (예: `feat(api): add price compare`, `fix(infra-cdk): correct Cognito password policy`).
4. 브랜치를 푸시합니다: `git push origin feat/<scenario-or-fix>`.
5. 시나리오 영향과 인프라 변경 사항을 설명하는 Pull Request를 엽니다.

## 라이선스

이 프로젝트는 MIT License로 배포됩니다 — 자세한 내용은 [LICENSE](LICENSE) 파일을 참고하시기 바랍니다.

## 연락처

- 메인테이너: [whchoi98](https://github.com/whchoi98)
- 이슈: <https://github.com/whchoi98/ontology-retail/issues>
- 이메일: whchoi98@gmail.com

<!-- harness-eval-badge:start -->
![Harness Score](https://img.shields.io/badge/harness-8.8%2F10-green)
![Harness Grade](https://img.shields.io/badge/grade-A-green)
![Last Eval](https://img.shields.io/badge/eval-2026--05--09-blue)
<!-- harness-eval-badge:end -->
