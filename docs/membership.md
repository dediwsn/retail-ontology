# Membership Layer (Phase 2A)

회원·등급·캠페인·거래·접점으로 구성된 멤버쉽 레이어의 설계와 구현 문서. 5-페르소나 데모 스파인 위에 *개체 단위* 데이터를 얹어 churn(이탈 위험) · acquisition(획득 ROI) · tier-up(등급 상승) 시나리오를 코히런트하게 묶는 것이 목적입니다.

> 관련 문서: [architecture.md](architecture.md) (전체 시스템) · [api-reference.md](api-reference.md) (엔드포인트 시그니처) · [data/CLAUDE.md](../data/CLAUDE.md) (적재기 규약).

## 1. 개요

| 축 | 이전(Phase 1·2) | 이후(Phase 2A) |
|---|---|---|
| 구매자 표현 | `Persona` 5종 (원형/세그먼트) | `Persona` 5종 + `Member` 1,000명(개체) |
| 마케팅 | 없음 | `Campaign` 20건 + `Touchpoint` 10,021건 |
| 거래 | 없음 | `Transaction` 7,862건 (Member ↔ Product) |
| 동작 시나리오 | A–H (검색·매칭·물류 등) | + I (churn) · J (acquisition) · K (tier-up) |

핵심 설계 결정:

- **Member ↔ Persona 는 N:1 옵셔널** — 한 명의 Member는 0 또는 1개의 Persona에 매칭. 페르소나 스위치 시 데이터 슬라이스가 자연스럽게 따라옵니다.
- **RFM 모델을 1급 속성으로 박음** — `recency_days`, `frequency`, `monetary_krw`가 노드 속성이라 Cypher만으로 분석 가능 (앱 레이어 어그리게이션 불필요).
- **`churn_risk`는 그래프-사이드에서 미리 계산** — `data/synthetic/membership.py:_churn_risk()`가 결정론적으로 채움. 라우터는 정렬·필터만 하면 되어 응답 시간이 안정적.
- **모든 ID·확률은 SHA1 시드 PRNG** — 같은 시드면 같은 출력. ECS 재로드 시 데모 흐름 보존.
- **`ANCHOR_DATE = 2026-04-01`** — 모든 `recency_days`·`joined_at`·캠페인 기간이 이 날짜를 기준으로 계산. 시간이 지나도 데모는 안정적.

## 2. 도메인 모델

원본: [`data/schemas.py`](../data/schemas.py) Phase 2A 블록 (line 162–226).

### 2.1 노드

#### `MembershipTier` — 회원 등급
| 필드 | 타입 | 비고 |
|---|---|---|
| `tier_id` | str | `tier_bronze` / `tier_silver` / `tier_gold` / `tier_vip` |
| `name_ko` | str | "브론즈" / "실버" / "골드" / "VIP" |
| `name_en` | `Literal["Bronze","Silver","Gold","VIP"]` | UI/쿼리 키 |
| `threshold_krw` | int | LTV 누진 임계 (0 / 500k / 2M / 5M) |
| `discount_rate` | float | 0.00 / 0.03 / 0.05 / 0.08 |

#### `Member` — 개별 회원
| 필드 | 타입 | 비고 |
|---|---|---|
| `member_id` | str | `mem_<6-char-sha1>` |
| `name_ko`, `age`, `gender` | str/int/Literal | 한국어 이름 풀 + `Gender = "F"|"M"` |
| `tier` | TierName | `name_en`과 동일 어휘 — 등급은 LTV 임계로 결정 |
| `persona_id` | Optional[str] | 5-페르소나 매칭(없을 수 있음) |
| `joined_at`, `last_purchase_at` | date / Optional[date] | ANCHOR_DATE 기준 역산 |
| **`recency_days`** | int | 최근 구매로부터 경과일 — RFM의 R |
| **`frequency`** | int | 누적 거래 수 — RFM의 F |
| **`monetary_krw`** | int | 누적 거래 금액 — RFM의 M |
| `ltv_krw` | int | 라이프타임 누적 — tier 결정에 사용 |
| `churn_risk` | float (0–1) | RFM + tier 보정으로 사전 계산 |
| `primary_channel_id` | Optional[str] | 주 사용 채널 |

#### `Campaign` — 마케팅 캠페인
| 필드 | 타입 | 비고 |
|---|---|---|
| `campaign_id` | str | `cmp_001` … `cmp_020` |
| `type` | `Literal["acquisition","retention","winback"]` | 분포 5/12/3 |
| `channel` | `Literal["email","push","sms","kakao"]` | kakao 비중 우세 |
| `start`, `end` | date | ANCHOR_DATE 기준 역산 |
| `cost_krw` | int | 캠페인 예산 |
| `target_persona_ids` | List[str] | 빈 리스트면 전체 대상 |

#### `Transaction` — 거래
`transaction_id` · `member_id` · `sku_id` · `amount_krw` · `ts` · `channel_id?`

#### `Touchpoint` — 마케팅 접점
`touchpoint_id` · `member_id` · `campaign_id?` · `type` (`email`/`push`/`sms`/`kakao`/`visit`) · `ts` · `responded: bool`

### 2.2 엣지 (Neptune)

```
(Member)-[:BELONGS_TO]->(MembershipTier)
(Member)-[:MATCHES_PERSONA]->(Persona)             # 옵셔널
(Member)-[:PREFERS_CHANNEL]->(Channel)             # 옵셔널
(Member)-[:MADE]->(Transaction)
(Transaction)-[:OF_PRODUCT]->(Product)             # 기존 Product 노드와 연결
(Member)-[:HAS_TOUCHPOINT]->(Touchpoint)
(Touchpoint)-[:FROM_CAMPAIGN]->(Campaign)          # 캠페인 외 접점은 미연결
(Campaign)-[:TARGETS]->(Persona)                   # 페르소나 타깃 캠페인
```

설계 의도:

- `Transaction`을 별도 노드로 둔 이유 — 회원-상품 *이력*을 다대다로 펼쳐야 lift 분석(`tier-up`)과 attribution(`acquisition`)이 그래프-사이드에서 가능.
- `Touchpoint` ↔ `Transaction`은 **직접 엣지가 없음**. attribution은 시간 윈도우(같은 회원의 touchpoint.ts 이후 transaction.ts)로 *추론*. 의도적 단순화.
- `Campaign-[TARGETS]->Persona`는 *기획* 메타데이터, `Touchpoint-[FROM_CAMPAIGN]->Campaign`은 *실행* 사실. 둘을 분리해야 "기획 타깃 vs 실제 응답자"가 비교 가능.

## 3. 합성 데이터 생성

원본: [`data/synthetic/membership.py`](../data/synthetic/membership.py) (439줄, 모두 결정론).

### 3.1 결정론 PRNG

```python
def _stable_int(*parts: str, mod: int) -> int:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % mod
```

모든 `member_id`, tier 선택, RFM 값, 거래 분배, 응답 여부가 이 함수의 키 조합으로 결정. 같은 시드 → 같은 출력.

### 3.2 RFM → churn risk

```python
def _churn_risk(recency_days, frequency, tier) -> float:
    base = clamp(recency_days / 180.0, 0.05, 0.95)        # R 가중
    freq_penalty = -0.20 if frequency >= 20 else \
                   -0.10 if frequency >= 10 else 0.0      # F 보정
    tier_floor   = -0.05 if tier == "VIP" else 0.0        # 의도된 보정
    return clamp(base + freq_penalty + tier_floor, 0.02, 0.98)
```

VIP에 `tier_floor: -0.05`를 더한 것은 *현실 반영*이 아니라 *데모 코히런스*용 — "VIP 이탈 방지 컨시어지" 캠페인의 ROI 곡선이 깔끔해지도록.

### 3.3 의도된 편향

- `_persona_tier_bias()` — 페르소나마다 tier 분포 다름.
  - 임산부 → Gold/VIP 비중↑
  - 4세 아이 엄마 → Silver/Gold 중심
  - 캠퍼 → Silver↑
  - 민감성 피부 → Gold↑
  - 글루텐 알레르기 → 균등
  → 페르소나 스위치 시 *눈에 보이는* 분포 차이 발생.

- **at-risk 비율 ~30%** — 회원 중 약 30%가 `recency_days > 90`. tier가 높을수록 이 비율이 낮아지는 자연스러운 그라디언트 (VIP < Gold < Silver < Bronze).

- **Touchpoint 응답률 — tier별 고정 베이스**
  | Tier | base response |
  |---|---|
  | VIP | 0.32 |
  | Gold | 0.24 |
  | Silver | 0.13 |
  | Bronze | 0.07 |
  → 캠페인 효과 분석이 안정된 곡선을 그림.

- **캠페인 분포** — 20건 = acquisition 5 / retention 12 / winback 3 (실제 한국 리테일의 60·25·15 비중에 가깝도록 의도).

### 3.4 출력 파일

```
data/output/
├── tiers.json          (4 records,    564 B)
├── members.json        (1,000 records, 386 KB)
├── campaigns.json      (20 records,    5 KB)
├── transactions.json   (7,862 records, 1.4 MB)
└── touchpoints.json    (10,021 records, 1.7 MB)
```

`output/`은 gitignore에서 *제외* — ground-truth 참조본으로 커밋. 이미지 빌드 시 S3 (`ontology-retail-dev-synthetic-data-<account>/data/output/`)에도 동기화.

## 4. Neptune 적재 흐름

원본: [`data/load.py:265–355`](../data/load.py).

적재는 **외래키 의존 순서**로 진행 — Persona / Product / Channel은 이전 단계에서 이미 MERGE된 상태라고 가정합니다.

```
1. tiers       → MERGE (n:MembershipTier {tier_id})
2. campaigns   → MERGE (n:Campaign)  + (Campaign)-[TARGETS]->(Persona)
3. members     → MERGE (n:Member)
                  + (Member)-[BELONGS_TO]->(MembershipTier)
                  + (Member)-[MATCHES_PERSONA]->(Persona)   # optional
                  + (Member)-[PREFERS_CHANNEL]->(Channel)   # optional
4. transactions → MERGE (n:Transaction) WITH n
                  MATCH (mb:Member) MERGE (mb)-[MADE]->(n)
                  MATCH (p:Product)  MERGE (n)-[OF_PRODUCT]->(p)
5. touchpoints  → MERGE (n:Touchpoint) WITH n
                  MATCH (mb:Member) MERGE (mb)-[HAS_TOUCHPOINT]->(n)
                  + (Touchpoint)-[FROM_CAMPAIGN]->(Campaign) # optional
```

### 4.1 규약

- **`_flatten_props`** — Neptune은 nested property를 지원하지 않으므로 list는 콤마 join 문자열로 강제.
- **모든 외래키는 `MATCH` 후 `MERGE`** — `MERGE … MERGE …` 한 줄 체이닝은 *추가 노드 생성 위험*이 있어 `MATCH` 방식으로 분리.
- **`tier_name_to_id` 매핑** — Member.`tier` 필드는 `name_en`("Bronze"…)이지만 MembershipTier 노드의 키는 `tier_id`("tier_bronze"…). load 단에서 변환.
- **Cypher 파라미터**는 항상 키워드 dict (`{"id": ..., "p": plain}`). [CLAUDE.md](../CLAUDE.md) Cypher 규약과 동일.

### 4.2 실행

```bash
# 한 번에 (commerce + logistics + membership 모두 적재)
python -m data.load --neptune --opensearch --from-s3
```

운영에서는 ECS one-shot 태스크로 실행 — VPC 안에서 Neptune에 직접 도달 가능 (외부 EC2는 도달 불가).

## 5. API 라우터 및 시나리오 매핑

| 시나리오 | 라우터 | 엔드포인트 | 사용 데이터 |
|---|---|---|---|
| **I. churn (이탈 위험 진단)** | [`api/routers/churn.py`](../api/routers/churn.py) | `GET /api/churn/dashboard`, `GET /api/churn/member/{id}` | `Member.churn_risk` 정렬 + 페르소나·tier 버킷 + 추천 winback 캠페인 |
| **J. acquisition (획득 ROI)** | [`api/routers/acquisition.py`](../api/routers/acquisition.py) | `GET /api/acquisition/dashboard` | `Campaign.cost_krw` ÷ 응답 `Touchpoint` 수 + 페르소나별 ROI |
| **K. tier-up (등급 상승 경로)** | [`api/routers/tier_up.py`](../api/routers/tier_up.py) | `GET /api/tier-up/dashboard` | Gold ÷ Silver lift (상품·카테고리 단위) + Silver 후보 |

### 5.1 churn 라우터의 핵심 모델

```python
HIGH_RISK = 0.7   # 1000명 중 ~24%가 이 임계 이상
```

응답 모델: `ChurnSummary` · `AtRiskMember[]` · `PersonaRiskBucket[]` · `TierRiskBucket[]` · `RecommendedCampaign[]` + Cytoscape contract `{nodes, edges}` subgraph.

### 5.2 tier-up 라우터의 lift 모델

```python
CANDIDATE_LTV_FLOOR = 1_500_000   # Gold 임계 2M의 75% — 상위 후보군
```

`product_lift = gold_buyers / silver_buyers` (코호트 크기로 정규화). 시간-시계열 tier 전이 데이터가 *없으므로* 현재 Gold 코호트를 post-transition, Silver를 pre-transition으로 *간주* — counterfactual 단순화.

### 5.3 라우터 등록

[`api/main.py:70–72`](../api/main.py)에 churn / acquisition / tier_up 라우터가 모두 `prefix="/api"`로 등록.

## 6. 객체 탐색기 / 온톨로지 메타 노출

### 6.1 객체 탐색기 ([`api/routers/objects.py:_TYPE_REGISTRY`](../api/routers/objects.py))

`/api/objects/{type}` 가 받는 5개 신규 type:

| 슬러그 | label | 정렬 키 |
|---|---|---|
| `member` | `Member` | `churn_risk DESC, ltv_krw DESC` (이탈 위험 회원 우선) |
| `tier` | `MembershipTier` | `threshold_krw ASC` |
| `campaign` | `Campaign` | `start DESC` (rank_score = 도달 touchpoint 수) |
| `transaction` | `Transaction` | `ts DESC, amount_krw DESC` |
| `touchpoint` | `Touchpoint` | `responded DESC, ts DESC` |

`Transaction` / `Touchpoint`는 사람-읽기 좋은 이름이 없어 `id`를 `name_prop`으로 사용 — 객체 탐색기는 합성 라벨을 표시.

### 6.2 온톨로지 메타 ([`api/routers/ontology.py:_CLASSES`/`_RELATIONS`](../api/routers/ontology.py))

5개 신규 클래스 등록:

```python
{"label": "Member",         "ko": "회원",        "color": "#f97316", "domain": "membership"},
{"label": "MembershipTier", "ko": "회원등급",    "color": "#facc15", "domain": "membership"},
{"label": "Campaign",       "ko": "캠페인",      "color": "#d946ef", "domain": "membership"},
{"label": "Transaction",    "ko": "거래",        "color": "#38bdf8", "domain": "membership"},
{"label": "Touchpoint",     "ko": "마케팅 접점", "color": "#c084fc", "domain": "membership"},
```

`domain: "membership"` 태그로 ER 다이어그램에서 같은 도메인끼리 묶이도록.

### 6.3 프론트엔드 노출

- **사이드바**: `web/components/Sidebar.tsx` "객체 탐색" 섹션 + 시나리오 I·J·K.
- **객체 카드**: `web/app/objects/[type]/page.tsx` 의 `TYPE_META` 가 슬러그 → 한국어 라벨 매핑.
- **시나리오 페이지**: `web/app/churn/page.tsx`, `web/app/acquisition/page.tsx`, `web/app/tier-up/page.tsx` 가 라우터 응답을 소비.
- **Cytoscape**: 멤버쉽 노드 색은 [Section 6.2 색]과 동일 토큰 — `web/components/graph/CytoscapeView.tsx` 의 `ONTOLOGY_STYLE`에 라벨 셀렉터 추가하면 일관됨.

## 7. 데이터 볼륨

| 노드/엣지 | 개수 |
|---|---:|
| `MembershipTier` | 4 |
| `Member` | 1,000 |
| `Campaign` | 20 |
| `Transaction` | 7,862 |
| `Touchpoint` | 10,021 |
| `Member-MADE-Transaction` | 7,862 |
| `Transaction-OF_PRODUCT-Product` | 7,862 |
| `Member-HAS_TOUCHPOINT-Touchpoint` | 10,021 |
| `Touchpoint-FROM_CAMPAIGN-Campaign` | ~9,500 (캠페인 외 접점 제외) |

총 멤버쉽 노드 ~19k, 엣지 ~36k. Neptune `db.r6g.large` 단일 인스턴스에서 dashboard 쿼리 응답 < 200ms.

## 8. 한계 및 의도된 단순화

설계상 *덜* 만든 것들 — 데모 범위(30–60분 PoC)에 맞춘 결정.

| 항목 | 단순화 | 운영 시스템에서 보강이 필요하다면 |
|---|---|---|
| 시간-시계열 tier 전이 | 없음 — 모든 회원은 *현재* tier만 보유 | 별도 `TierHistory` 노드 또는 Member에 `tier_history: [{tier, since}]` 추가 |
| Touchpoint → Transaction 인과 | 직접 엣지 없음, 시간 윈도우 추론만 | `(Touchpoint)-[ATTRIBUTED_TO]->(Transaction)` (decay window + 모델 학습) |
| 회원 위치 | `Member`에 region/주소 없음 → 시나리오 H 물류와 직접 연결 불가 | `(Member)-[LIVES_IN]->(Region)` 추가, Warehouse 도달 거리 계산 |
| 다중 페르소나 | `MATCHES_PERSONA`는 0–1개 | 카디널리티 N:M으로 변경 (그래프 자체는 이미 지원, Pydantic만 List[str]로) |
| Channel 이력 | `primary_channel_id` 단일값 | `(Member)-[USED_CHANNEL {ts, count}]->(Channel)` 다중 엣지 |
| 가족·관계 | 없음 | `(Member)-[FAMILY_OF]->(Member)` — 4세 아이 엄마 시나리오 강화 |
| Guardrail/PII | 합성 한국어 이름 사용 — 가명 | 운영 데이터는 마스킹 + Bedrock Guardrail 입력 스크럽 |

## 9. 멤버쉽 레이어 확장 체크리스트

새 멤버쉽 노드 타입을 추가할 때 이 순서로 갱신 — [data/CLAUDE.md](../data/CLAUDE.md)와 [CLAUDE.md auto-sync rules](../CLAUDE.md#auto-sync-rules) 결합:

1. [`data/schemas.py`](../data/schemas.py) — Pydantic 모델 추가, Phase 2A 블록 안.
2. [`data/synthetic/membership.py`](../data/synthetic/membership.py) — 결정론적 generator 추가, `ANCHOR_DATE` + `_stable_int` 시드 사용.
3. [`data/load.py`](../data/load.py) — `load_membership` 안에 MERGE Cypher 추가, 외래키 의존 순서 유지.
4. [`api/routers/objects.py:_TYPE_REGISTRY`](../api/routers/objects.py) — 객체 탐색기 등록 + 정렬 키 정의.
5. [`api/routers/ontology.py:_CLASSES`/`_RELATIONS`](../api/routers/ontology.py) — `domain: "membership"` 태그.
6. [`web/components/Sidebar.tsx`](../web/components/Sidebar.tsx) — 객체 탐색 섹션 추가.
7. [`web/app/objects/[type]/page.tsx`](../web/app/objects/[type]/page.tsx) — `TYPE_META` 매핑.
8. (선택) 새 시나리오 라우터 — `api/routers/<scenario>.py` 추가, `api/main.py` 등록, 페이지/사이드바/가이드 투어/`api-reference.md` 갱신.
9. `data/output/<entity>.json` 재생성 후 `tests/test_smoke.py`에 router 임포트 스모크 테스트 추가.
10. 회귀 검증: `pytest tests -q && python -m compileall -q api data scripts`.

## 변경 이력

| 일자 | 변경 |
|---|---|
| 2026-04 | Phase 2A 초기 도입 — Member·Tier·Campaign·Transaction·Touchpoint 5종 + 7종 엣지. churn/acquisition/tier-up 라우터 동시 추가. |
| 2026-05 | 본 설계 문서 작성. |
