'use client';

// 5-minute guided tour — multi-step modal walking through scenarios A→G.
// Triggered by a button in the topbar; auto-shows on first ever visit
// (localStorage gate).

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Play, X, ChevronLeft, ChevronRight, Search, MessageSquare, BarChart3,
  UserCheck, ShieldAlert, ArrowLeftRight, Store, BookOpen, Map,
  TrendingDown, Wallet, ArrowUpRight, MapPin,
} from 'lucide-react';

const STORAGE_KEY = 'ontology-retail.tour-seen';

type Step = {
  badge: string;
  ko: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  // 30-60s pitch — what this scenario demonstrates and what to try first.
  pitch: string;
  try_it: string;
  tech: string;
};

const STEPS: Step[] = [
  {
    badge: '시작',
    ko: '5분 가이드 투어',
    href: '/',
    icon: Map,
    pitch: 'Korean Retail/CPG 온톨로지 데모입니다 — Bedrock + AgentCore + Neptune 위에 7개 wow 시나리오가 올라갑니다. 각 단계에서 "이 시나리오 열기"를 눌러 살펴보고 "다음"으로 돌아오세요.',
    try_it: '우상단 페르소나 선택을 한 번 정해두면 모든 시나리오가 그 페르소나 가중치를 적용합니다.',
    tech: 'Next.js 14 + FastAPI + Bedrock Sonnet 4.6 + AgentCore Memory/Code Interpreter + Neptune + OpenSearch Serverless',
  },
  {
    badge: 'A',
    ko: '의미 검색',
    href: '/search',
    icon: Search,
    pitch: '한국어 자연어 쿼리를 BM25(Nori) + Cohere KNN 하이브리드로 인덱싱하고 Bedrock Reranker로 정렬합니다. 결과는 Knowledge Graph 1-hop 시각화와 함께 표시됩니다.',
    try_it: '"임산부도 안전한 비건 토너" 풍선을 누르면 phase 타임라인이 실시간으로 BM25/KNN/RRF/Reranker 진행을 보여줍니다.',
    tech: 'OpenSearch Serverless · Cohere embed-v4 · cohere.rerank-v3',
  },
  {
    badge: 'B',
    ko: '대화형 에이전트',
    href: '/chat',
    icon: MessageSquare,
    pitch: 'Bedrock Converse 다회차 + AgentCore Memory short/long-term + 4개 tool(memory_recall, neptune_subgraph, semantic_search, kb_lookup)을 도구 호출 SSE로 스트리밍합니다.',
    try_it: '"임신 6개월인데 나한테 맞는 스킨케어 추천해줘" — 우측 패널에 도구 호출이 토큰별로 표시됩니다.',
    tech: 'Bedrock Converse Stream · AgentCore Memory · 4 tool definitions',
  },
  {
    badge: 'C',
    ko: 'MD 인사이트',
    href: '/insights',
    icon: BarChart3,
    pitch: 'Neptune 트렌드 집계 → Sonnet 4.6 한국어 MD 요약 (토큰 스트리밍) → AgentCore Code Interpreter 샌드박스에서 matplotlib + NanumGothic으로 실 PNG 차트 → 1-hop 드릴다운.',
    try_it: '"지난 4주간 20대 여성에게 검색 빈도가 급증한 성분 Top10" — 답변이 토큰별로 흐른 뒤 차트가 도착합니다.',
    tech: 'Neptune openCypher · Bedrock Converse Stream · AgentCore Code Interpreter Firecracker microVM',
  },
  {
    badge: 'D',
    ko: '페르소나 매칭',
    href: '/match',
    icon: UserCheck,
    pitch: '40개 합성 페르소나(임산부/4세아이/캠퍼/...)에 대해 HAS_CONCERN 그래프 워크 + 가중 ranking으로 "이 사람을 위한 SKU"를 산출합니다.',
    try_it: '리스트에서 페르소나 하나를 클릭 — 우측에 그래프 explanation과 추천 SKU가 함께 나옵니다.',
    tech: 'Neptune graph traversal · weighted persona-product affinity',
  },
  {
    badge: 'E',
    ko: '안전성 렌즈',
    href: '/safety',
    icon: ShieldAlert,
    pitch: '카페인/알코올/임산부 금기 성분 등 Safety Profile에 따라 SKU를 필터링하고 위험 등급을 표시합니다. Guardrail 출력 스크럽이 함께 적용됩니다.',
    try_it: '"임산부 금기" 프로파일을 선택하면 카페인/레티놀/알코올 함유 SKU가 빨간 등급으로 묶여 보입니다.',
    tech: 'Bedrock Guardrails · KFDA + INCI ingredient blacklists',
  },
  {
    badge: 'F',
    ko: '대체재 추천',
    href: '/substitute',
    icon: ArrowLeftRight,
    pitch: '특정 SKU를 입력하면 같은 카테고리·같은 효능·다른 브랜드의 대체재를 가격 차이와 함께 제안합니다. "재고 없을 때 대안"의 가장 자연스러운 패턴.',
    try_it: '샘플 SKU 풍선 하나를 누르면 +/- 가격 비교 카드가 나옵니다.',
    tech: 'Neptune 1-hop substitution traversal · price delta',
  },
  {
    badge: 'G',
    ko: '가격·가용성 비교',
    href: '/price',
    icon: Store,
    pitch: '자연어 → 추천 SKU → CU·이마트·올리브영·마컬 4채널의 가격/할인/재고 매트릭스 + 페르소나 선호 채널 가중치 점수.',
    try_it: '페르소나를 "임산부"로 두고 "비건 토너 추천" 검색 — 마트/올영이 페르소나 보너스 받아 BEST로 표시됩니다.',
    tech: 'Neptune AVAILABLE_IN edges · deterministic price synthesis · persona-channel bias',
  },
  {
    badge: 'I',
    ko: '이탈 위험 진단',
    href: '/churn',
    icon: TrendingDown,
    pitch: '1,000명 합성 회원에 RFM(Recency·Frequency·Monetary) 기반 churn_risk가 적재되어 있습니다. 등급별·페르소나별 위험 분포 + 상위 30명 클릭 드릴다운 + Cytoscape 1-hop 그래프 + 페르소나 맞춤 winback 캠페인 추천을 한 화면에 묶어 보여줍니다.',
    try_it: '상위 위험 회원 리스트에서 VIP 한 명을 클릭 — 우측에 1-hop 그래프와 추천 winback이 동시에 갱신됩니다.',
    tech: 'Neptune openCypher 5-round-trip aggregation · Member ↔ Tier ↔ Persona ↔ Touchpoint ↔ Campaign',
  },
  {
    badge: 'J',
    ko: '확보 채널 ROI',
    href: '/acquisition',
    icon: Wallet,
    pitch: 'acquisition 캠페인별 비용 대비 확보 회원 LTV로 ROI를 산출하고, 페르소나×채널 응답률 매트릭스 히트맵으로 "임산부 페르소나는 카카오톡 푸시가 이메일 대비 N배" 같은 채널 효율 차이를 직관화합니다.',
    try_it: '히트맵 셀에 마우스를 올리면 "응답/발송"의 절대치가 함께 보입니다. 채널별 ROI 카드와 캠페인별 ROI 카드를 비교해 어디에 다음 예산을 태울지 판단하세요.',
    tech: 'Neptune cohort rollup · single-touch attribution · Persona × Channel matrix',
  },
  {
    badge: 'K',
    ko: '등급 상승 경로',
    href: '/tier-up',
    icon: ArrowUpRight,
    pitch: 'Gold 회원이 Silver 회원 대비 더 많이 사는 카테고리·상품을 lift(per-capita 비교)로 산출해 "등급 상승 시그널"을 식별하고, LTV 1.5M~2M 사이 Silver 회원을 "업그레이드 후보"로 함께 추출합니다.',
    try_it: '상품 lift 차트에서 가장 높은 lift를 보이는 SKU 1-2개를 메모 — 그 카테고리를 어떤 후보에게 추천할지 매핑해 보세요.',
    tech: 'Cohort lift (Gold rate ÷ Silver rate) with Laplace smoothing · LTV gap-to-Gold candidate ranking',
  },
  {
    badge: 'L',
    ko: '회원-거점 커버리지',
    href: '/coverage',
    icon: MapPin,
    pitch: '페르소나 컨텍스트로 필터링된 회원의 시도별 분포를 한국 지도에 코로플레스로 그리고, 같은 지도 위에 Warehouse 마커를 겹쳐 "내 페르소나 회원 중 N km 안에 거점이 없는 비율"을 한 KPI로 노출합니다. 멤버쉽·물류·페르소나를 한 화면에서 직조하는 *허브* 시나리오.',
    try_it: '페르소나를 "캠퍼"로 두면 강원·경상·제주 색이 짙어지고 거점 갭이 드러납니다. 차원 토글(회원 수 / 평균 이탈 / 평균 LTV / 미도달 비율)과 반경 슬라이더로 같은 지도에서 4개 보기를 비교해 보세요.',
    tech: 'Member.region_id × Region centroid · haversine to nearest Warehouse · persona-biased KOSTAT 17-sido distribution',
  },
  {
    badge: '메타',
    ko: '온톨로지 / 객체 탐색 / 운영',
    href: '/schema',
    icon: BookOpen,
    pitch: '시나리오 외에도 — 온톨로지 ER 다이어그램 / 표준 매핑 CSV 브라우저 / 매핑 검증 리포트 / 8가지 객체 탐색 / 비용 모니터 / 도구 호출 트레이스가 좌측 사이드바에 모두 들어 있습니다.',
    try_it: '먼저 /schema에서 12개 클래스의 ER을 둘러보고, /validation에서 매핑 커버리지 % 를 확인해 보세요.',
    tech: 'Cytoscape ER · Cost Explorer · in-process trace ring buffer',
  },
];

export function GuidedTour() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  // Auto-show once on first ever visit.
  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) {
        // Small delay so the page paints first.
        const t = setTimeout(() => setOpen(true), 500);
        return () => clearTimeout(t);
      }
    } catch { /* ignore */ }
  }, []);

  const closeAndRemember = () => {
    setOpen(false);
    try { localStorage.setItem(STORAGE_KEY, '1'); } catch { /* ignore */ }
  };

  const cur = STEPS[step];
  const Icon = cur.icon;

  return (
    <>
      <button
        onClick={() => { setStep(0); setOpen(true); }}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-accent-500/40 bg-accent-500/10 text-accent-200 text-xs font-medium hover:bg-accent-500/15 transition"
        title="5분 가이드 투어"
      >
        <Play className="w-3.5 h-3.5" />
        가이드
      </button>

      {open && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="relative w-full max-w-2xl mx-4 rounded-xl border border-ink-700 bg-ink-900 shadow-2xl">
            <button
              onClick={closeAndRemember}
              className="absolute top-3 right-3 p-1.5 rounded hover:bg-ink-800 text-ink-400"
              aria-label="닫기"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="p-7">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-accent-400 to-accent-600 flex items-center justify-center">
                  <Icon className="w-5 h-5 text-ink-950" />
                </div>
                <div>
                  <div className="text-[10px] font-mono tracking-wider text-accent-300">
                    {cur.badge} · {step + 1} / {STEPS.length}
                  </div>
                  <h2 className="text-xl font-bold text-ink-50">{cur.ko}</h2>
                </div>
              </div>

              <p className="text-sm leading-relaxed text-ink-200 mb-4">{cur.pitch}</p>

              <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 mb-3">
                <div className="text-[10px] font-mono uppercase tracking-wider text-emerald-300 mb-1">
                  지금 해보기
                </div>
                <p className="text-xs text-ink-200">{cur.try_it}</p>
              </div>

              <div className="text-[10px] font-mono text-ink-500 mb-5">
                {cur.tech}
              </div>

              <div className="flex items-center justify-between gap-2">
                <button
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                  disabled={step === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-ink-700 text-ink-300 text-xs disabled:opacity-30 hover:bg-ink-800"
                >
                  <ChevronLeft className="w-3.5 h-3.5" /> 이전
                </button>

                <Link
                  href={cur.href}
                  onClick={() => closeAndRemember()}
                  className="px-3 py-1.5 rounded bg-accent-500 text-ink-950 text-xs font-semibold hover:bg-accent-400"
                >
                  이 시나리오 열기 →
                </Link>

                {step < STEPS.length - 1 ? (
                  <button
                    onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-ink-800 border border-ink-700 text-ink-100 text-xs hover:border-accent-500"
                  >
                    다음 <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                ) : (
                  <button
                    onClick={closeAndRemember}
                    className="px-3 py-1.5 rounded bg-emerald-500 text-ink-950 text-xs font-semibold hover:bg-emerald-400"
                  >
                    완료
                  </button>
                )}
              </div>

              <div className="mt-5 flex justify-center gap-1">
                {STEPS.map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setStep(i)}
                    className={[
                      'h-1.5 rounded-full transition-all',
                      i === step ? 'w-8 bg-accent-400' : 'w-1.5 bg-ink-700 hover:bg-ink-600',
                    ].join(' ')}
                    aria-label={`스텝 ${i + 1}`}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
