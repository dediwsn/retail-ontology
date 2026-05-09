import Link from 'next/link';
import {
  Search, MessageSquare, BarChart3, UserCheck, ShieldAlert, ArrowLeftRight,
  Store, Truck, TrendingDown, Wallet, ArrowUpRight,
  Network, ArrowRight, Package, FlaskConical, HeartPulse, TrendingUp, Tag,
  Layers, Users, Building2, MessageCircle, MapPin, Boxes, CalendarClock,
  UserCircle, Crown, Megaphone, Receipt, Send, Target,
} from 'lucide-react';

// Home dashboard — rebuilt from the 4/28 deployed image structure:
//   1. header bar with status indicator
//   2. title block (uppercase tag + h1 + description)
//   3. scenario cards grid (A–H plus new I/J/K)
//   4. Knowledge Graph object types section (commerce / lifestyle / logistics
//      / membership), with the 5 new membership types added.

type Scenario = {
  href: string;
  tag: string;
  title: string;
  desc: string;
  color: 'blue' | 'emerald' | 'amber' | 'violet' | 'rose' | 'cyan' | 'sky' | 'teal' | 'orange' | 'fuchsia' | 'yellow' | 'lime' | 'indigo';
  icon: React.ComponentType<{ className?: string }>;
};

const SCENARIOS: Scenario[] = [
  { href: '/search',     tag: 'A', title: '의미 검색',         desc: '한국어 자연어 → BM25(Nori) + Cohere KNN 하이브리드 + Bedrock Reranker → 1-hop 그래프 시각화.', color: 'blue',     icon: Search },
  { href: '/chat',       tag: 'B', title: '대화형 에이전트',     desc: 'Bedrock Converse + AgentCore Memory 다회차 + 4개 도구 호출 SSE 스트리밍.',                color: 'emerald',  icon: MessageSquare },
  { href: '/insights',   tag: 'C', title: 'MD 인사이트',        desc: 'Neptune 트렌드 집계 + Sonnet 4.6 토큰 스트리밍 + AgentCore Code Interpreter 차트.',         color: 'amber',    icon: BarChart3 },
  { href: '/match',      tag: 'D', title: '페르소나 매칭',      desc: '40 합성 페르소나의 Concern + 선호/회피 성분 그래프 워크 → 가중 SKU 추천.',                color: 'violet',   icon: UserCheck },
  { href: '/safety',     tag: 'E', title: '안전성 렌즈',        desc: '임산부·어린이·글루텐프리·비건·민감성 프로파일 → AVOIDS_INGREDIENT 그래프 → 위반 highlight.', color: 'rose',     icon: ShieldAlert },
  { href: '/substitute', tag: 'F', title: '대체재 추천',        desc: '같은 카테고리·다른 브랜드 + 성분/관심사 겹침 + 가격 차이로 대안 5–8개.',                  color: 'cyan',     icon: ArrowLeftRight },
  { href: '/price',      tag: 'G', title: '가격·가용성 비교',   desc: '자연어 → 추천 SKU → 4채널(CU/이마트/올영/마컬) 가격·할인·재고 매트릭스.',                color: 'sky',      icon: Store },
  { href: '/logistics',  tag: 'H', title: '물류 네트워크',      desc: '제조사 DC → 3PL 허브 → 채널 RDC → Last-mile 거점을 한국 지도에 시각화 + lane + KPI.',     color: 'teal',     icon: Truck },
  { href: '/churn',      tag: 'I', title: '이탈 위험 진단',     desc: 'RFM 기반 churn_risk + VIP/Gold 분포 + 페르소나 맞춤 winback 캠페인 추천.',               color: 'orange',   icon: TrendingDown },
  { href: '/acquisition',tag: 'J', title: '확보 채널 ROI',      desc: 'Campaign × Channel × Persona 매트릭스 — 카카오톡 푸시 vs 이메일 ROI 직관화.',           color: 'fuchsia',  icon: Wallet },
  { href: '/tier-up',    tag: 'K', title: '등급 상승 경로',     desc: 'Silver → Gold lift + LTV ≥ 1.5M 업그레이드 후보 추출 (per-capita Laplace smoothing).',  color: 'yellow',   icon: ArrowUpRight },
  { href: '/coverage',   tag: 'L', title: '회원-거점 커버리지', desc: '회원 시도 분포 + Warehouse 마커 오버레이 + radius 슬라이더 — "내 페르소나 회원 중 N km 안에 거점 없는 비율" 단일 KPI.', color: 'lime',     icon: MapPin },
  { href: '/vip',        tag: 'M', title: 'VIP 타깃 빌더',    desc: '외부 소비 패널 + 멤버쉽 wallet share — Opportunity VIP(점유율 < 30%·총액 > 임계) 식별. 같은 데이터로 5가지 VIP 정의 운용.', color: 'indigo',   icon: Target },
];

// Color-class mappings — Tailwind needs literal class strings; this lets
// TypeScript catch typos and the bundler include all variants.
const CARD_COLOR: Record<Scenario['color'], string> = {
  blue:     'from-blue-500/20 to-blue-500/0 border-blue-500/40',
  emerald:  'from-emerald-500/20 to-emerald-500/0 border-emerald-500/40',
  amber:    'from-amber-500/20 to-amber-500/0 border-amber-500/40',
  violet:   'from-violet-500/20 to-violet-500/0 border-violet-500/40',
  rose:     'from-rose-500/20 to-rose-500/0 border-rose-500/40',
  cyan:     'from-cyan-500/20 to-cyan-500/0 border-cyan-500/40',
  sky:      'from-sky-500/20 to-sky-500/0 border-sky-500/40',
  teal:     'from-teal-500/20 to-teal-500/0 border-teal-500/40',
  orange:   'from-orange-500/20 to-orange-500/0 border-orange-500/40',
  fuchsia:  'from-fuchsia-500/20 to-fuchsia-500/0 border-fuchsia-500/40',
  yellow:   'from-yellow-500/20 to-yellow-500/0 border-yellow-500/40',
  lime:     'from-lime-500/20 to-lime-500/0 border-lime-500/40',
  indigo:   'from-indigo-500/20 to-indigo-500/0 border-indigo-500/40',
};

type ObjectType = {
  href: string;
  label_en: string;
  label_ko: string;
  count: string;
  color: string; // hex for inline style (matches Sidebar palette)
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
};

const OBJECT_GROUPS: { title: string; types: ObjectType[] }[] = [
  {
    title: '상거래 코어',
    types: [
      { href: '/objects/product',      label_en: 'Product',      label_ko: '상품 (250)',          color: '#60a5fa', icon: Package },
      { href: '/objects/brand',        label_en: 'Brand',        label_ko: '브랜드 (60)',         color: '#f472b6', icon: Tag },
      { href: '/objects/manufacturer', label_en: 'Manufacturer', label_ko: '제조사 (30)',         color: '#94a3b8', icon: Building2 },
      { href: '/objects/category',     label_en: 'Category',     label_ko: '카테고리',            color: '#94a3b8', icon: Layers },
    ],
  },
  {
    title: '라이프스타일',
    types: [
      { href: '/objects/persona',    label_en: 'Persona',    label_ko: '페르소나 (40)',  color: '#fb923c', icon: Users },
      { href: '/objects/concern',    label_en: 'Concern',    label_ko: '관심사/효능',    color: '#fbbf24', icon: HeartPulse },
      { href: '/objects/trend',      label_en: 'Trend',      label_ko: '트렌드',         color: '#a78bfa', icon: TrendingUp },
      { href: '/objects/ingredient', label_en: 'Ingredient', label_ko: '성분',           color: '#34d399', icon: FlaskConical },
    ],
  },
  {
    title: '리뷰 / 채널',
    types: [
      { href: '/objects/review',  label_en: 'Review',  label_ko: '리뷰 (2,480)', color: '#facc15', icon: MessageCircle },
      { href: '/objects/channel', label_en: 'Channel', label_ko: '채널 (4)',     color: '#22d3ee', icon: Store },
    ],
  },
  {
    title: '물류 / 이벤트',
    types: [
      { href: '/objects/region',    label_en: 'Region',    label_ko: '지역 (17)',     color: '#0ea5e9', icon: MapPin },
      { href: '/objects/warehouse', label_en: 'Warehouse', label_ko: '물류센터 (30)', color: '#14b8a6', icon: Boxes },
      { href: '/objects/carrier',   label_en: 'Carrier',   label_ko: '운송사 (7)',    color: '#06b6d4', icon: Truck },
      { href: '/objects/event',     label_en: 'Event',     label_ko: '이벤트 (12)',   color: '#ec4899', icon: CalendarClock },
    ],
  },
  {
    title: '멤버십 / 마케팅 — 신규',
    types: [
      { href: '/objects/member',      label_en: 'Member',         label_ko: '회원 (1,000)',     color: '#f97316', icon: UserCircle },
      { href: '/objects/tier',        label_en: 'MembershipTier', label_ko: '회원등급 (4)',     color: '#facc15', icon: Crown },
      { href: '/objects/campaign',    label_en: 'Campaign',       label_ko: '캠페인 (20)',      color: '#d946ef', icon: Megaphone },
      { href: '/objects/transaction', label_en: 'Transaction',    label_ko: '거래 (7,862)',     color: '#38bdf8', icon: Receipt },
      { href: '/objects/touchpoint',  label_en: 'Touchpoint',     label_ko: '접점 (10,021)',    color: '#c084fc', icon: Send },
    ],
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 border-b border-ink-700 bg-ink-900 flex items-center px-6">
        <div className="text-xs text-ink-400">홈 / 대시보드</div>
        <div className="ml-auto flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5 text-ink-300">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-soft" />
            All systems operational
          </span>
        </div>
      </header>

      <div className="flex-1 px-8 py-10 max-w-7xl mx-auto w-full">
        <div className="mb-8">
          <p className="text-xs uppercase tracking-[0.2em] text-accent-400 mb-2 font-semibold">
            Korean Retail / CPG · Ontology Demo
          </p>
          <h1 className="text-4xl font-bold text-ink-50 leading-tight mb-3">
            편의점 · 마트 · 드럭스토어 · 프리미엄 새벽배송 데이터를<br />
            <span className="text-accent-300">온톨로지 그래프</span>로 풀어내는 데모
          </h1>
          <p className="text-ink-300 leading-relaxed">
            GS1 GPC + FoodOn + INCI + schema.org 표준에 한국 어댑터(KFDA / 식약처)를 매핑한 합성 데이터로,
            13개 시나리오(의미 검색 → VIP 타깃 빌더)와 19종 Knowledge Graph 객체 탐색을 한 화면에 제공합니다.
            좌측 사이드바에서 객체 타입을 탐색하거나, 아래 시나리오 카드에서 바로 진입하세요.
          </p>
        </div>

        <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
          {SCENARIOS.map((s) => {
            const Icon = s.icon;
            return (
              <Link
                key={s.href}
                href={s.href}
                className={`group relative rounded-lg border bg-gradient-to-br ${CARD_COLOR[s.color]} bg-ink-800 p-5 hover:bg-ink-700/60 transition`}
              >
                <div className="flex items-start gap-3 mb-3">
                  <div className="w-10 h-10 rounded-md bg-ink-900 border border-ink-700 flex items-center justify-center shrink-0">
                    <Icon className="w-5 h-5 text-accent-300" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] uppercase tracking-wider text-accent-400 font-semibold">
                      시나리오 {s.tag}
                    </div>
                    <h3 className="text-base font-bold text-ink-50">{s.title}</h3>
                  </div>
                  <ArrowRight className="w-4 h-4 text-ink-400 group-hover:text-accent-300 group-hover:translate-x-0.5 transition shrink-0" />
                </div>
                <p className="text-xs text-ink-300 leading-relaxed">{s.desc}</p>
              </Link>
            );
          })}
        </section>

        <section className="mb-10">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-ink-100 flex items-center gap-2">
              <Network className="w-5 h-5 text-accent-400" />
              Knowledge Graph 객체 타입
            </h2>
            <span className="text-xs text-ink-400">19 types · Neptune openCypher · 합성 데이터</span>
          </div>

          {OBJECT_GROUPS.map((g) => (
            <div key={g.title}>
              <div className="text-[10px] uppercase tracking-wider text-ink-500 font-semibold mb-1.5 mt-3">
                {g.title}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
                {g.types.map((t) => {
                  const Icon = t.icon;
                  return (
                    <Link
                      key={t.href}
                      href={t.href}
                      className="group rounded-md bg-ink-800 border border-ink-700 px-3 py-2.5 flex items-center gap-2 hover:border-accent-500/60 hover:bg-ink-700/40 transition"
                    >
                      <div
                        className="w-7 h-7 rounded flex items-center justify-center shrink-0"
                        style={{ backgroundColor: `${t.color}22`, border: `1px solid ${t.color}55` }}
                      >
                        <Icon className="w-3.5 h-3.5" style={{ color: t.color }} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-semibold text-ink-100 truncate">{t.label_en}</div>
                        <div className="text-[10px] text-ink-400 truncate">{t.label_ko}</div>
                      </div>
                      <ArrowRight className="w-3 h-3 text-ink-500 group-hover:text-accent-400 group-hover:translate-x-0.5 transition shrink-0" />
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </section>

        <footer className="border-t border-ink-700 pt-6 text-xs text-ink-400">
          본 데모의 SKU·리뷰·페르소나·회원·캠페인은 합성 데이터입니다. 공공 표준
          (GS1 GPC, FoodOn, INCI, schema.org) + 식약처 한국 어댑터 매핑.
        </footer>
      </div>
    </div>
  );
}
