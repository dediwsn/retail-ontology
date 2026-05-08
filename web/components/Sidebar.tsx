'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Search, MessageSquare, BarChart3, Network, Package, FlaskConical,
  HeartPulse, TrendingUp, Tag, Layers, Users, Store, Database,
  ShieldCheck, Brain, Activity, Home, ChevronRight, Sparkles,
  UserCheck, ShieldAlert, ArrowLeftRight, BookOpen, GitBranch,
  Building2, MessageCircle, ListTree, Truck, MapPin, Boxes, CalendarClock,
  UserCircle, Crown, Megaphone, Receipt, Send, TrendingDown, Wallet, ArrowUpRight,
  Target,
} from 'lucide-react';

import { SidebarAuth } from './SidebarAuth';

type Item = {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  badge?: string;
  match?: (path: string) => boolean;
};

type Section = { title: string; items: Item[] };

// Palantir Foundry-style left rail: grouped sections with icons + active
// indicator. The first three sections drive the demo flows; the lower
// sections expose the underlying Knowledge Graph object types — clicking
// any opens a 1-hop neighborhood in the graph view.
const SECTIONS: Section[] = [
  {
    title: '시나리오 (Scenarios)',
    items: [
      { href: '/',           icon: Home,           label: '홈' },
      { href: '/search',     icon: Search,         label: '의미 검색',     badge: 'A' },
      { href: '/chat',       icon: MessageSquare,  label: '대화형 에이전트', badge: 'B' },
      { href: '/insights',   icon: BarChart3,      label: 'MD 인사이트',    badge: 'C' },
      { href: '/match',      icon: UserCheck,      label: '페르소나 매칭',   badge: 'D' },
      { href: '/safety',     icon: ShieldAlert,    label: '안전성 렌즈',    badge: 'E' },
      { href: '/substitute', icon: ArrowLeftRight, label: '대체재 추천',    badge: 'F' },
      { href: '/price',      icon: Store,          label: '가격·가용성 비교', badge: 'G' },
      { href: '/logistics',  icon: Truck,          label: '물류 네트워크',   badge: 'H' },
      { href: '/churn',      icon: TrendingDown,   label: '이탈 위험 진단', badge: 'I' },
      { href: '/acquisition',icon: Wallet,         label: '확보 채널 ROI',  badge: 'J' },
      { href: '/tier-up',    icon: ArrowUpRight,   label: '등급 상승 경로', badge: 'K' },
      { href: '/coverage',   icon: MapPin,         label: '회원-거점 커버리지', badge: 'L' },
      { href: '/vip',        icon: Target,         label: 'VIP 타깃 빌더',  badge: 'M' },
    ],
  },
  {
    title: '메타 (Ontology)',
    items: [
      { href: '/schema',     icon: GitBranch,  label: '온톨로지 스키마' },
      { href: '/standards',  icon: BookOpen,   label: '표준 매핑' },
      { href: '/validation', icon: ShieldCheck, label: '검증 리포트' },
    ],
  },
  {
    title: '객체 탐색 (Knowledge Graph)',
    items: [
      { href: '/objects/product',    icon: Package,      label: '상품 (Product)' },
      { href: '/objects/ingredient', icon: FlaskConical, label: '성분 (Ingredient)' },
      { href: '/objects/concern',    icon: HeartPulse,   label: '관심사/효능 (Concern)' },
      { href: '/objects/trend',      icon: TrendingUp,   label: '트렌드 (Trend)' },
      { href: '/objects/brand',      icon: Tag,          label: '브랜드 (Brand)' },
      { href: '/objects/category',   icon: Layers,       label: '카테고리 (Category)' },
      { href: '/objects/persona',    icon: Users,        label: '페르소나 (Persona)' },
      { href: '/objects/channel',    icon: Store,        label: '채널 (Channel)' },
      { href: '/objects/manufacturer', icon: Building2,    label: '제조사 (Manufacturer)' },
      { href: '/objects/review',     icon: MessageCircle, label: '리뷰 (Review)' },
      { href: '/objects/region',     icon: MapPin,        label: '지역 (Region)' },
      { href: '/objects/warehouse',  icon: Boxes,         label: '물류센터 (Warehouse)' },
      { href: '/objects/carrier',    icon: Truck,         label: '운송사 (Carrier)' },
      { href: '/objects/event',      icon: CalendarClock, label: '이벤트 (Event)' },
      // Membership / marketing layer
      { href: '/objects/member',      icon: UserCircle,   label: '회원 (Member)' },
      { href: '/objects/tier',        icon: Crown,        label: '회원등급 (Tier)' },
      { href: '/objects/campaign',    icon: Megaphone,    label: '캠페인 (Campaign)' },
      { href: '/objects/transaction', icon: Receipt,      label: '거래 (Transaction)' },
      { href: '/objects/touchpoint',  icon: Send,         label: '접점 (Touchpoint)' },
    ],
  },
  {
    title: '파이프라인 (Ops)',
    items: [
      { href: '/ops/ingest',     icon: Database,    label: '데이터 적재' },
      { href: '/ops/guardrail',  icon: ShieldCheck, label: '가드레일' },
      { href: '/ops/memory',     icon: Brain,       label: '메모리 히스토리' },
      { href: '/ops/eval',       icon: Activity,    label: '평가 결과' },
      { href: '/ops/trace',      icon: ListTree,    label: '도구 호출 트레이스' },
    ],
  },
];

function isActive(pathname: string, item: Item): boolean {
  if (item.match) return item.match(pathname);
  if (item.href === '/') return pathname === '/';
  return pathname === item.href || pathname.startsWith(item.href + '/');
}

export function Sidebar() {
  const pathname = usePathname() ?? '/';
  return (
    <aside className="w-72 shrink-0 bg-ink-900 border-r border-ink-700 flex flex-col">
      <div className="h-14 flex items-center px-5 border-b border-ink-700">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-accent-400 to-accent-600 flex items-center justify-center">
            <Network className="w-4 h-4 text-ink-950" />
          </div>
          <div>
            <div className="text-sm font-semibold text-ink-100 leading-tight">Ontology Retail</div>
            <div className="text-[10px] text-ink-400 leading-tight">Korean CPG Demo · v0.5.0</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-3">
        {SECTIONS.map((section) => (
          <div key={section.title} className="mb-4">
            <div className="px-5 mb-1.5 text-[10px] uppercase tracking-wider text-ink-400 font-semibold">
              {section.title}
            </div>
            <ul>
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={[
                        'flex items-center gap-2.5 mx-2 px-3 py-2 rounded text-sm transition-colors',
                        active
                          ? 'bg-accent-500/10 text-accent-200 ring-1 ring-accent-500/30'
                          : 'text-ink-200 hover:bg-ink-800 hover:text-ink-100',
                      ].join(' ')}
                    >
                      <Icon className={`w-4 h-4 ${active ? 'text-accent-400' : 'text-ink-400'}`} />
                      <span className="flex-1">{item.label}</span>
                      {item.badge && (
                        <span className={[
                          'text-[10px] font-mono px-1.5 py-0.5 rounded',
                          active ? 'bg-accent-500/20 text-accent-300' : 'bg-ink-700 text-ink-300',
                        ].join(' ')}>
                          {item.badge}
                        </span>
                      )}
                      {active && <ChevronRight className="w-3 h-3 text-accent-400" />}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-ink-700 px-4 py-3">
        <div className="flex items-center gap-2 text-[11px] text-ink-400">
          <Sparkles className="w-3 h-3 text-accent-400 shrink-0" />
          <span className="truncate">합성 데이터 · GS1 GPC + FoodOn + INCI</span>
        </div>
      </div>

      <SidebarAuth />
    </aside>
  );
}
