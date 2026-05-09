# AWS 자원 상세 가이드

이 프로젝트가 사용 중인 AWS 자원 각각의 **역할 / 선택 이유 / 시나리오 매핑**을 담은 가이드. [docs/architecture.md](architecture.md)의 시스템 개요와 짝을 이룹니다 — architecture는 layer 간 관계, 이 문서는 layer 내부의 자원별 책임.

---

## 0. 전체 구성 한 눈에

- **계정**: `<account-id>` (production-track demo)
- **Primary 리전**: `ap-northeast-2` (Seoul) — 대부분 자원
- **Edge 리전**: `us-east-1` — Lambda@Edge + ACM 인증서 (CloudFront 요건)
- **CDK 스택 6개**: `Network → Data → Ai → Compute → Edge + Observability`
- **항상 켜진 baseline 비용**: ~770 USD/월 (Neptune이 가장 큼)

---

## 1. Edge & Auth — 사용자 진입 계층

### CloudFront Distribution (`<distribution-id>`)

브라우저가 가장 먼저 만나는 layer. 기능:

- **TLS 종단** — `*.whchoi.net` ACM 인증서로 HTTPS 처리, ALB로는 HTTP-80 forward (데모 트레이드오프, [SECURITY.md](../SECURITY.md)에 production 마이그레이션 계획)
- **Viewer + Origin caching** — 정적 자산은 edge에서, 동적 API는 pass-through
- **Origin lock-down** — `X-Origin-Auth-Token` (Secrets Manager 백킹) 커스텀 헤더를 ALB로 주입 → ALB는 이 헤더 + CF 관리 prefix list만 통과시킴 → ALB DNS를 직접 알아내도 우회 불가
- **커스텀 도메인**: `retail-ontology.whchoi.net`

### Lambda@Edge (`AuthEdgeFn`, us-east-1)

CloudFront viewer-request 트리거:

- **쿠키 기반 인증 게이트** — `id_token` 쿠키 없으면 Cognito Hosted UI로 302 리다이렉트
- **`PUBLIC_PATHS` 화이트리스트는 의도적으로 좁음** — `callback`, `logout`, `_next`, `favicon`, `api/health` 만 우회. **루트 경로 `/`는 게이트되며**, 따라서 미인증 viewer는 SPA 셸을 받지 않고 즉시 Cognito로 redirect됩니다. [ADR-0012](decisions/0012-lambda-edge-root-gate-and-logout.md) 참조
- **us-east-1 강제 배치** — Lambda@Edge 요건. CDK `experimental.EdgeFunction`이 CloudFront와 별도 sibling stack 생성
- **[ADR-0003](decisions/0003-lambda-edge-stable-id-hardcode-strategy.md)**: Cognito 식별자(user_pool_id, client_id, domain)를 inline 코드에 hardcode (Lambda@Edge가 SSM/Secrets 못 읽기 때문). drift detection은 CDK output(`UserPoolId`, `UserPoolClientId`, `UserPoolDomain`)이 매 deploy 시 노출

### Cognito User Pool (`<user-pool-id>`)

신원 발행·검증 layer:

- **OAuth 2.0 Authorization Code grant + Hosted UI**
- **RS256 JWT** — JWKS는 1시간 TTL 캐시 (키 회전 대응)
- **데모 사용자**: `demo / demo@whchoi.net`, 비밀번호 정책 8자 (production은 더 강하게)
- **App Client ID는 Lambda@Edge inline + API env 양쪽에서 사용** — ADR-0003이 Lambda@Edge 측 hardcode trade-off 명시 (API 측은 required env로 강제)
- **Cognito는 PUT semantics** — `update-user-pool-client`가 미지정 필드를 null로 clobber. 그래서 ALL Cognito 변경은 CDK only ([ADR-0004](decisions/0004-cognito-user-pool-client-cdk-driven.md))
- **Hosted UI Logout URL** — `https://<PUBLIC_DOMAIN>/`(슬래시 포함) 등록 필수. `/api/auth/logout`이 이 URL로 바운스하므로 누락 시 로그아웃 후 빈 화면

### Auth Router (`/api/auth/*`, FastAPI 측)

Cognito Hosted UI 보완용 ApplicationAPI 4개 엔드포인트. 모두 [ADR-0012](decisions/0012-lambda-edge-root-gate-and-logout.md)에 정리:

- **`/api/auth/login`** — 사이드바 재인증 진입점, `/oauth2/authorize` 302
- **`/api/auth/callback`** — Hosted UI에서 받은 `?code=` 를 토큰 교환 + `id_token` / `access_token` / `refresh_token` 3종 쿠키 (HttpOnly, Secure, SameSite=Lax) 설정 후 `/`로 302
- **`/api/auth/logout`** — 3종 쿠키 모두 삭제 + Cognito Hosted UI `/logout` 302 (IdP 세션도 무효화)
- **`/api/auth/whoami`** — 항상 JSON 200 — `{authenticated: true, sub, email, username, groups}` 또는 `{authenticated: false}`. 절대 401을 던지지 않음 (Sidebar 위젯이 미인증 상태를 정상 UI 분기로 렌더할 수 있도록)

### ACM Certificate

- **us-east-1 발급** (CloudFront 요건). Wildcard `*.whchoi.net`
- DNS 검증, 자동 갱신

### Route 53

- **Hosted Zone**: `whchoi.net` 위에 ALIAS 레코드로 `retail-ontology.whchoi.net` → CloudFront distribution
- 도메인 변경 시 4개 surface 정합성: DNS, CF alias, Cognito callback, API `PUBLIC_DOMAIN` env (auto-sync rule in [CLAUDE.md](../CLAUDE.md))

---

## 2. Compute — 애플리케이션 실행 계층

### ECS Cluster (`ontology-retail-dev-cluster`)

Fargate 모드, 2개 서비스 호스팅.

### ECS Service: API (`ontology-retail-dev-api`)

- **Fargate ARM64**, 2-replica
- **이미지**: 단일 ECR 이미지가 두 역할 — API 서버 OR command override로 일회성 데이터 로더 (단일 이미지 두 역할 트레이드오프)
- **uvicorn + FastAPI**, 19개 라우터 (scenarios A–M + objects + ontology + ops + auth + health + ingest; vip 라우터가 시나리오 M 5종 VIP 정의 모두 호스팅)
- **Bedrock + Neptune + OpenSearch + AgentCore** 모두 호출
- **Pydantic Settings**가 startup에 모든 env 검증 — fail-fast

### ECS Service: Web (`ontology-retail-dev-web`)

- **Fargate ARM64**, 2-replica
- **Next.js 14 App Router standalone build**
- 시나리오 A–M + Knowledge Graph 객체 탐색기 + 운영 콘솔 + `/codegraph` 메타 페이지 + 사이드바 설정 가능 회사 로고 (CompanyLogo, 4 SVG 프리셋)
- API와 같은 ALB 뒤, path-based routing (`/api/*` → API, 나머지 → Web)

### Application Load Balancer

- **HTTP-80 origin** (TLS는 CloudFront 종단)
- **Security Group**: AWS 관리 prefix list `com.amazonaws.global.cloudfront.origin-facing`만 허용 — 내 ALB DNS를 직접 알아내도 거부
- ALB Access Logs → S3 (30일 후 Glacier transition)

### ECR Repositories

- `ontology-retail-dev-api`, `ontology-retail-dev-web` 각 1개씩
- ARM64 manifest, **`:latest` + SHA-pinned tag** 동시 push (deterministic rollout 위해 task definition은 SHA pin)

> **왜 ARM64?** Graviton2/3 가격 대비 성능이 약 20–40% 우위. Python(uvicorn)과 Node.js(Next.js)는 둘 다 ARM 네이티브. 단점은 빌드 시 `--platform linux/arm64` 플래그를 잊으면 ECS가 거부하는 것 — 그래서 [CLAUDE.md](../CLAUDE.md)에 "ARM64 everywhere" 규칙이 있고 CI에서도 검증.

---

## 3. Data & Search — 지식그래프 + 하이브리드 검색

### Amazon Neptune (`ontology-retail-dev-neptune`)

**프로젝트의 핵심 차별점.** 그래프 DB.

- **단일 인스턴스 dev sizing** (`db.r6g.large` 등)
- **openCypher 엔드포인트** — Neo4j 호환 query
- **IAM SigV4 인증** — boto3 `neptunedata` 클라이언트 사용 (수동 SigV4 서명 안 됨 — 일찍 학습한 gotcha)
- **19개 노드 클래스**: Product, Ingredient, Concern, Trend, Brand, Category, Persona, Channel, Manufacturer, Review + 물류층 (Region, Warehouse, Carrier, Route, Shipment, Event, Inventory)
- **약 5,000 노드 / 10,000 엣지**
- **Private subnet 전용** — laptop에서 직접 접근 불가, ECS one-shot loader를 같은 SG에서 실행
- **모든 Cypher**: `parameters={...}` keyword arg로 전달 (포지셔널은 TypeError, 인젝션 방지). 자세한 규약은 [.claude/skills/cypher-conventions.md](../.claude/skills/cypher-conventions.md)

### OpenSearch Serverless (`<opensearch-collection-id>`)

하이브리드 검색의 BM25 + KNN layer.

- **Serverless 모드** — capacity 자동 관리, 인덱싱 시 OCU 사용
- **인덱스**: `ontology-retail-dev-kb-index`, single sharded
- **Nori Korean analyzer** — BM25 어휘 매칭에 한국어 형태소 분석
- **Cohere `embed-v4` 1024차원 KNN** — 의미 검색
- **RRF (Reciprocal Rank Fusion)**로 BM25+KNN 결합 → Cohere `rerank-v3`이 top 50을 재정렬 → 최종 top 10
- **Auto-id only** — custom `_id` 거부 (AOSS 제약, 일찍 학습)

### Aurora PostgreSQL Serverless v2 (`ontology-retail-dev-aurora`)

- 세션 메타데이터 + Cognito 사용자 매핑
- ACU 0.5–16 자동 스케일
- **비밀**은 Secrets Manager에서 startup에 fetch (env에 평문 저장 안 함)

### S3 Buckets (4개)

| 버킷 용도 | 내용 | Lifecycle |
|---|---|---|
| `raw-docs` | Bedrock Knowledge Base 적재 소스 (PDF, MD) | KB가 자동 sync |
| `uploads` | 사용자 업로드 (시나리오에서 사용) | 30일 후 Glacier |
| `synthetic-data` | 로더 소스 (products/reviews/personas + logistics) | 버전 관리 |
| `ontology-snapshots` | 버전 관리된 ontology dump | 무기한 |

추가로 **ALB access logs용** 버킷도 별도 존재.

### KMS Keys

- 각 데이터 자원마다 customer-managed key (Aurora, S3, OpenSearch, CloudWatch logs)
- 자동 회전 enabled
- IAM 정책으로 ECS task role만 사용 가능

---

## 4. AI & Memory — 데모의 핵심

### Bedrock Foundation Models

| 모델 | 용도 | 호출 위치 |
|---|---|---|
| **Sonnet 4.6** (`global.anthropic.claude-sonnet-4-6`) | 채팅(B), 인사이트(C)의 Korean answer 생성 + 도구 호출 | `api/services/agent.py` |
| **Cohere `embed-v4`** (1024d, `global.cohere.embed-v4:0`) | 쿼리 + 문서 임베딩 (KNN feeder) | `api/services/search.py` |
| **Cohere `rerank-v3`** (cross-region inference profile) | RRF 후 top-K 재정렬 | `api/services/search.py` (실패 시 RRF 순서 유지하며 fallback) |

> Sonnet 4.6은 **never Haiku-Lite** ([CLAUDE.md](../CLAUDE.md) 규칙). 채팅·인사이트 모두 동일 모델 — analytical voice quality 일관성 유지.

### Bedrock Knowledge Base (`<knowledge-base-id>`)

- `raw-docs` S3 위에 managed RAG
- 자동 청킹·임베딩·OpenSearch 적재
- API의 `kb_lookup` agent tool로 호출

### Bedrock Guardrails (`<guardrail-id>`)

- Input scrub: 채팅·검색 — PII / harmful content 거름
- Output scrub: 인사이트 answer — 부적절 콘텐츠 차단
- 실패는 non-fatal (요청 자체를 막지 않음, 로그만)

### AgentCore Memory (`ontology_retail_dev_memory-<suffix>`)

**시나리오 B 다회차 채팅의 핵심.**

- **Short-term**: 세션별 이벤트 (대화 흐름)
- **Long-term**: 사용자 namespace에 정착되는 fact (예: "이 사용자는 임산부 페르소나")
- **TTL 7일**
- **CDK 통합 gotcha** ([ADR-0001](decisions/0001-agentcore-memory-via-aws-custom-resource.md)) — L2 construct 없어 `AwsCustomResource` v3 explicit form, IAM은 `bedrock-agentcore:*` (not `bedrock-agentcore-control:*`), 이름은 underscore-only regex
- **네임스페이스 변수**: `{actorId}` + `{sessionId}` (NOT `userId`)

### AgentCore Code Interpreter

- **Firecracker microVM** — 매 호출마다 격리된 sandbox
- **matplotlib + NanumGothic 폰트** 번들 — 한글 차트 렌더 가능
- **시나리오 C**: Sonnet이 trend 데이터를 chart_spec으로 만들면 Code Interpreter가 실제 PNG 생성

> 이 4개 Bedrock primitive(Sonnet + Cohere embed + Cohere rerank + Knowledge Base) + 2개 AgentCore primitive(Memory + Code Interpreter)가 동시에 협주하는 것이 이 데모의 *진짜 가치*입니다. 다른 클라우드는 이걸 단일 매니지드 surface로 제공 못 합니다 (각각 다른 서비스로 직접 조립해야 함). "Knowledge Graph + RAG + Agent + 차트 생성"이 한 화면에서 작동하는 게 영업 hook.

---

## 5. Networking — VPC 토폴로지

### VPC + Subnets

- **CIDR**: `10.20.0.0/16`
- **2 AZ** (`ap-northeast-2a`, `ap-northeast-2c`)
- **Public subnets**: ALB, NAT
- **Private (with-egress) subnets**: ECS tasks (api/web), VPC endpoints
- **Private (isolated) subnets**: Neptune, Aurora (인터넷 접근 자체 불가)

### NAT Gateway

- **단일 NAT** (NAT EIP 1개) — 비용 vs HA 트레이드오프 (production은 AZ별 NAT 권장)
- ECS tasks의 outbound (Bedrock, ECR pull)에 사용

### VPC Endpoints (Interface)

ECS tasks가 AWS 서비스를 NAT 경유 없이 호출:

- `s3` (Gateway endpoint, free)
- `secretsmanager`, `ssm`, `kms`, `logs`, `ecr.api`, `ecr.dkr`, `bedrock-runtime`
- 비용: Interface endpoint은 시간당 ~$0.01/AZ + GB transfer

### Security Groups (계층 분리)

| SG | Ingress 허용 |
|---|---|
| `albSg` | 80/443 from CF prefix list만 |
| `webSg`, `apiSg` | ALB SG에서만 |
| `auroraSg` | apiSg에서만 5432 |
| `neptuneSg` | apiSg에서만 8182 |
| `vpceSg` | apiSg, webSg에서만 443 |

각 SG가 다음 SG의 source가 되는 *체인 패턴* — production grade.

---

## 6. Security & Secrets

### Secrets Manager

| 비밀 | 용도 |
|---|---|
| Origin auth token | CloudFront → ALB X-Origin-Auth-Token 헤더 값 |
| Aurora password | startup에 API가 fetch |

각 secret은 개별 회전 정책. Origin auth secret 캐시는 **5분 TTL** (이전엔 무한 lru_cache로 오래된 값을 사용하는 버그 있었음 — `50a059a` 커밋에서 수정).

### IAM 구조

- **API task role**: Bedrock invoke, Neptune read/write, OpenSearch index, Secrets Manager read, S3 read/write per bucket, AgentCore invoke
- **Web task role**: 최소 권한 (CloudWatch logs만)
- **Lambda@Edge role**: CloudWatch logs (Lambda@Edge는 외부 API 호출 안 함)
- **Loader role**: API role이 그대로 (one-shot으로 같은 task definition 사용)

---

## 7. Observability & Cost

### CloudTrail

- **Management events only** (data events for Bedrock은 CloudTrail 이벤트 타입이 아님 — 이거 잘못 알아 시간 낭비한 일이 있어 [ADR-0002](decisions/0002-cloudtrail-via-cfntrail-with-manual-bucket-policy.md)로 정리)
- **L1 `CfnTrail`** 사용 (CDK 2.150 L2 버그 회피, 버킷 정책 수동 추가)
- **데니리스트로 보호**: `cloudtrail delete-trail*`, `stop-logging*`은 우리 deny list에서 차단 (audit-blinding 방지)

### CloudWatch Logs

- `/aws/ecs/ontology-retail-dev/api` — uvicorn + FastAPI logs
- `/aws/ecs/ontology-retail-dev/web` — Next.js logs
- AWS WAF logs (CloudFront 설정 시)
- Log group별 KMS 암호화

### CloudWatch Alarms (account-level)

- Bedrock Converse error rate
- Neptune CPU
- OpenSearch search-rate

### ALB Access Logs

- S3 보관 → 30일 후 Glacier transition

### AWS Cost Anomaly Detection

- `Default-Services-Monitor` 구독, email 알림
- 데모 budget guardrail

### AWS Budgets

- **월 1000 USD** 한도 설정 (`ObservabilityStack`에 `monthlyBudgetUsd: 1000`)

---

## 8. CDK 스택 책임 매핑

[infra-cdk/CLAUDE.md](../infra-cdk/CLAUDE.md)에서 stack별 명확 분리:

| Stack | 자원 | 의존 |
|---|---|---|
| **OntologyRetailNetwork** | VPC, subnets, NAT, VPC endpoints, SGs | (root) |
| **OntologyRetailData** | Neptune, OpenSearch, Aurora, S3, KMS keys | Network |
| **OntologyRetailAi** | Bedrock Guardrail, KB, AgentCore Memory | Data |
| **OntologyRetailCompute** | ECS cluster + services, ALB, ECR, IAM | Network + Data + Ai |
| **OntologyRetailEdge** | CloudFront, Lambda@Edge, Cognito | Compute (cross-region us-east-1) |
| **OntologyRetailObservability** | CloudTrail, CloudWatch alarms, Cost Anomaly | Compute + Data + Ai |

**테스트**: `infra-cdk/test/stacks.test.ts`가 6개 stack 모두 jest snapshot으로 검증 (CI에서 매 push마다).

---

## 9. 시나리오별 자원 사용 매트릭스

각 시나리오가 어떤 자원을 부르는지:

| | Neptune | OpenSearch | Bedrock Sonnet | Cohere Embed/Rerank | KB | Memory | Code Interp | AgentCore tools |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **A** Search | ✓ subgraph | ✓ BM25+KNN | | ✓ | | | | |
| **B** Chat | ✓ traversal | ✓ via tool | ✓ stream | ✓ | ✓ via tool | ✓ both | | semantic_search, kb_lookup, neptune_subgraph, memory_recall |
| **C** Insights | ✓ aggregation | | ✓ stream | | | | ✓ chart | |
| **D** Persona Match | ✓ HAS_CONCERN | | | | | | | |
| **E** Safety | ✓ traversal | | | | | | | + Guardrails on input |
| **F** Substitute | ✓ same-cat | | | | | | | |
| **G** Price | ✓ AVAILABLE_IN | | | | | | | |
| **H** Logistics | ✓ Route+Inv | | ✓ via panel | | | | | inventory_lookup, nearest_warehouses, shortest_path |

---

## 10. 비용 분포 (대략)

월 ~770 USD baseline 중 큰 항목:

1. **Neptune**: 가장 큼 (~250 USD/월, db.r6g.large 24/7)
2. **NAT Gateway** + Interface VPC endpoints: ~80–120 USD/월
3. **Aurora Serverless v2** ACU baseline: ~100 USD/월
4. **OpenSearch Serverless** OCU minimum: ~150 USD/월
5. ECS Fargate (4 task × ARM64 small): ~50 USD/월
6. CloudFront, ALB, S3, CloudWatch: 각 ~10–30 USD/월
7. Bedrock invoke: 사용량 기반 (데모 트래픽이 적어 소액)
8. AgentCore Memory: 메모리 저장량 기반 (데모는 낮음)

---

## 11. 데이터 소스

이 데모의 데이터는 **3축 — 표준 매핑 / 공공 데이터 / 합성 데이터**로 구성됩니다. 외부 권위 데이터를 한국어 도메인에 *bridging*하는 게 신뢰도의 핵심입니다.

### 11.1 외부 표준 매핑 (`ontology/mappings/`)

외부 표준 ID → 한국어 도메인 라벨 변환표. 모두 CSV/JSON으로 직접 검토 가능하며, `data/public/<adapter>.py` 어댑터가 로딩·정규화 책임을 짐.

| 표준 | 출처 | 매핑 파일 | 어댑터 | 용도 |
|---|---|---|---|---|
| **KFDA (식약처)** 식품 카테고리 | 식품의약품안전처 식품유형 분류체계 | `gs1-gpc-to-kfda-food.csv` (GS1↔KFDA bridge 포함) | [`data/public/kfda.py`](../data/public/kfda.py) | 시나리오 E (안전성 렌즈 — 임산부/영유아 차단 카테고리), `/validation` 검증 리포트의 GS1+KFDA 커버리지 |
| **GS1 GPC** (Global Product Classification) | GS1 공식 brick 분류 | `gs1-gpc-to-kfda-food.csv` | (kfda.py 와 공유) | 상품 카테고리 표준화 — 모든 Product 노드의 `gs1_brick` 속성 백본 |
| **INCI** (International Nomenclature of Cosmetic Ingredients) | EU·KR·US 공통 화장품 성분 표준 명명 | `inci-to-korean.csv` (영문 INCI ↔ 한국어 동의어) | [`data/public/inci.py`](../data/public/inci.py) | 시나리오 E 화장품 안전성 (임산부 위험 성분 인식), Cypher `inci:<slug>` 노드 ID 백본 |
| **FoodOn** (Food Ontology) | 오픈소스 음식 분류체계 (purl.obofoundry.org/obo/FOODON) | `foodon-to-korean.json` (219건 한국어 별칭) | [`data/public/foodon.py`](../data/public/foodon.py) | 시나리오 A·B 한국어 음식 검색 보조 어휘 (예: "milk" ↔ "우유" ↔ "락토프리") |
| **Beauty Categories** (자체 정제) | INCI + KFDA 화장품 카테고리 합성 | (코드 내장) | [`data/public/beauty_categories.py`](../data/public/beauty_categories.py) | 화장품 도메인 내부 분류 |

**검증 흐름**: `/validation` 엔드포인트가 4개 매핑(INCI / FoodOn / GS1+KFDA / Loader)의 `expected/covered/missing/severity` 커버리지를 실시간 보고. v0.1 → v1.0 게이트는 "30 wow 쿼리 통과 + ≥80% 검증" (프로젝트 메모리 참조).

### 11.2 공공 데이터

| 자원 | 출처 | 위치 | 용도 |
|---|---|---|---|
| **KOSTAT 행정구역 GeoJSON** | 통계청 17 시도 + 34 시군구 경계 | `web/public/korea-provinces.json` (146 KB), `ontology/mappings/korea-regions.csv` | 시나리오 H choropleth 지도 — `react-simple-maps` + `d3-geo`로 렌더링, 5:4 viewBox로 한반도 ~36°N 비율 자연 유지 |
| **Pretendard 폰트** | orioncactus/pretendard (오픈소스 한글 web font) | `web/public/fonts/pretendard-variable.woff2` | 프론트엔드 전반 한글 타이포그래피 |
| **NanumGothic 폰트** | Naver / Google Fonts 한글 무료 폰트 | `api/fonts/NanumGothic-Regular.ttf` | AgentCore Code Interpreter의 matplotlib 차트가 시나리오 C에서 한글 라벨 렌더 (NanumGothic 미번들 시 두부 ▮ 출력) |

### 11.3 합성 데이터 (`data/synthetic/`)

PoC 데모이므로 진짜 상품 DB를 쓸 수 없음. 대신 **결정적 seed 기반 합성** — 같은 코드는 같은 데이터를 만들어 wow 시나리오가 재현 가능하도록 함.

| 모듈 | 산출물 | 규모 | 핵심 디자인 |
|---|---|---|---|
| [`personas.py`](../data/synthetic/personas.py) | `data/output/personas.ndjson` | **5 wow + 35 supporting = 40 페르소나** | Wow 5인이 시나리오 A~H 전체의 narrative spine: psn_001 임산부 32세 / psn_002 워킹맘 글루텐알레르기 자녀 / psn_003 민감성 24세 / psn_004 헬스챌린저 35세 / psn_005 MD 40세. 각 페르소나는 `concerns` 그래프 노드로 모델링 |
| [`products.py`](../data/synthetic/products.py) | `data/output/products.ndjson` + 부속 JSON | **~250 SKU** + brands(30~) + manufacturers(15~) + categories | `is_wow` / `wow_moment` 컬럼이 wow 페르소나가 검색했을 때 *반드시 잡혀야 할* SKU를 표시. `scripts/eval_wow_queries.py`가 30 쿼리로 ≥85% 검증 |
| [`reviews.py`](../data/synthetic/reviews.py) | `data/output/reviews.ndjson` | **2,480 리뷰** | Bedrock이 페르소나 + SKU 조합으로 자연스러운 한국어 리뷰 생성 (`_bedrock.py`로 호출). `helpful_count` 분포로 ranking 신호 |
| [`logistics.py`](../data/synthetic/logistics.py) | `data/output/{regions,warehouses,carriers}.json` + Route/Shipment/Event/Inventory NDJSON | **17 sido + 34 sigungu, 30 창고, 7 운송사, 76 lane, 500 출하, 12 이벤트, 940 inventory rows** | 시나리오 H 물류 네트워크. 콜드체인 인지 inventory 분포, haversine k-NN을 위한 위경도 |
| [`channels.json`](../data/output/channels.json) | (정적) | 4 채널 (CU / 이마트 / 올리브영 / 마컬) | 시나리오 G 가격·가용성 매트릭스 |
| [`concerns.json`](../data/output/concerns.json) | (정적) | 페르소나 관심사 + 카테고리 | HAS_CONCERN 그래프 traversal |
| [`trends.json`](../data/output/trends.json) | (정적) | 28일 검색·구매 트렌드 | 시나리오 C MD 인사이트 입력 |
| [`_bedrock.py`](../data/synthetic/_bedrock.py) | (호출 헬퍼) | — | 합성 시 Bedrock Sonnet으로 한국어 텍스트 생성 |
| [`deterministic.py`](../data/synthetic/deterministic.py) | (시드 헬퍼) | — | 같은 ID는 같은 hash → 같은 결과. 재배포해도 페르소나 1번이 항상 같은 사람 |

**적재 흐름**: `data/load.py --neptune --opensearch --from-s3` — synthetic-data S3 버킷에서 NDJSON을 읽어 Neptune에 그래프 노드/엣지로, OpenSearch에 KNN+BM25 인덱스로 동시 적재. ECS one-shot 태스크로 실행 (private subnet의 Neptune 접근 가능).

### 11.4 Bedrock Knowledge Base 적재 문서 (`raw-docs` S3)

시나리오 B의 `kb_lookup` 도구가 호출하는 RAG 검색 대상.

- **콘텐츠**: 식품·화장품 도메인 PDF/MD (예: 제품 사양서, 안전성 가이드, 캠페인 자료)
- **자동 청킹·임베딩**: Bedrock KB가 Cohere `embed-v4`로 1024d 벡터화 후 OpenSearch 적재
- **수동 추가**: 새 PDF를 S3에 업로드 → `aws bedrock-agent start-ingestion-job` (또는 `scripts/sync_kb_datasource.sh`)

### 11.5 데이터 정합성 게이트

세 layer가 일관되어야 wow 시나리오가 작동:

1. **`/validation` 리포트** — 4개 매핑(INCI/FoodOn/GS1+KFDA/Loader)의 missing/severity (실시간)
2. **`/api/ops/eval` 리포트** — 30 wow 쿼리의 pass-rate (캐시 10분)
3. **`scripts/eval_wow_queries.py`** — `sys.exit(1)` at <85% (CI gate)
4. **`tests/api/test_models.py`** — Pydantic schema가 응답 shape 검증

이 4개 게이트가 모두 녹색이어야 데모가 *재현 가능한 신뢰성*을 갖습니다.

---

## 관련 문서

- 시스템 개요와 데이터 플로우: [docs/architecture.md](architecture.md)
- 4개 ADR (CDK 트레이드오프 결정): [docs/decisions/](decisions/)
- 6 CDK 스택 코드: [infra-cdk/lib/](../infra-cdk/lib/)
- 보안 트레이드오프 + production 마이그레이션: [SECURITY.md](../SECURITY.md)
- 시나리오별 API: [docs/api-reference.md](api-reference.md)
- 신규 기여자 온보딩: [docs/onboarding.md](onboarding.md)
- 합성 데이터 생성·적재 컨벤션: [data/CLAUDE.md](../data/CLAUDE.md)
- 표준 매핑 변경 시 체크리스트: [ontology/CLAUDE.md](../ontology/CLAUDE.md)
