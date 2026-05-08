'use client';

// Scenario L — Coverage Map (회원-거점 커버리지).
//
// 페르소나 컨텍스트로 필터링된 회원의 시도별 분포(코로플레스) + 거점 마커
// + 4개 차원 토글(count/churn/ltv/uncov) + radius 슬라이더 + 우측 상세 패널.
//
// 디자인 일관성:
//   • 시나리오 색 = sky/cyan 계열 (시나리오 H 물류와 같은 지도 모티프지만 색은 분리)
//   • 페이지 셸: min-h-screen flex flex-col + header.h-14 + max-w-[1500px]
//   • 페르소나는 web/lib/persona-context.tsx 의 useActivePersona() Context 사용

import { useEffect, useMemo, useState } from 'react';
import {
  MapPin, Users, AlertTriangle, Building2, Activity, Crown, Compass,
} from 'lucide-react';

import * as api from '@/lib/api-client';
import { KoreaMapView, Marker as MapMarker, RegionFill } from '@/components/map/KoreaMapView';
import { useActivePersona } from '@/lib/persona-context';

type Dim = api.CoverageDimension;

const DIM_LABEL: Record<Dim, string> = {
  count: '회원 수',
  churn: '평균 이탈 위험',
  ltv:   '평균 LTV',
  uncov: '미도달 비율',
};

const DIM_HUE: Record<Dim, RegionFill['hue']> = {
  count: 'cyan',
  churn: 'rose',
  ltv:   'amber',
  uncov: 'rose',
};

const WH_TYPE_LABEL: Record<string, string> = {
  mfr: '제조사 DC',
  rdc: '채널 RDC',
  '3pl': '3PL 허브',
  lastmile: 'Last-mile',
};

// 차원별로 region.value(0..1)를 계산. 각 차원의 max로 정규화 → 코로플레스 색이
// 항상 의미 있게 분포 (전체가 0.05 미만으로 깔리는 일이 없도록).
function regionFillsFor(
  regions: api.RegionCoverage[],
  dim: Dim,
): RegionFill[] {
  const raw = regions.map((r) => {
    switch (dim) {
      case 'count': return r.members;
      case 'churn': return r.avg_churn_risk;
      case 'ltv':   return r.avg_ltv_krw;
      case 'uncov': return r.covered ? 0 : r.members;  // 미도달 회원이 많을수록 짙게
    }
  });
  const max = Math.max(...raw, 1e-9);
  return regions.map((r, i) => ({
    region_code: r.region_code,
    value: raw[i] / max,
    hue: DIM_HUE[dim],
  }));
}

function formatKrw(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M원`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}k원`;
  return `${v}원`;
}

export default function CoveragePage() {
  const { active } = useActivePersona();
  const [dim, setDim] = useState<Dim>('count');
  const [radius, setRadius] = useState<number>(80);
  const [data, setData] = useState<api.CoverageDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.coverageDashboard({
      persona: active?.id ?? null,
      dimension: dim,
      radius_km: radius,
    })
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [active?.id, dim, radius]);

  const fills = useMemo<RegionFill[]>(
    () => (data ? regionFillsFor(data.regions, dim) : []),
    [data, dim],
  );

  const markers: MapMarker[] = useMemo(() => {
    if (!data) return [];
    return data.warehouses.map((w) => ({
      id: w.warehouse_id,
      name: w.name_ko,
      type: (['mfr', 'rdc', '3pl', 'lastmile'].includes(w.type)
        ? w.type
        : 'lastmile') as MapMarker['type'],
      coordinates: [w.lng, w.lat] as [number, number],
    }));
  }, [data]);

  const selected = useMemo(
    () => (selectedRegion ? data?.regions.find((r) => r.region_code === selectedRegion) : null),
    [data, selectedRegion],
  );

  const uncoveredTopN = useMemo(() => {
    if (!data) return [];
    return data.regions
      .filter((r) => !r.covered && r.members > 0)
      .sort((a, b) => b.members - a.members)
      .slice(0, 5);
  }, [data]);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 border-b border-ink-700 bg-ink-900 flex items-center px-6">
        <div className="text-xs text-ink-400">시나리오 L · 회원-거점 커버리지</div>
        <span className="ml-3 text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/30">
          17 시도 · {data?.warehouses.length ?? '…'} 거점 · 반경 {radius} km
        </span>
      </header>

      <div className="flex-1 px-6 py-6 max-w-[1500px] mx-auto w-full flex flex-col gap-5 min-h-0">
        <div>
          <h1 className="text-2xl font-bold text-ink-50 mb-1 flex items-center gap-2">
            <MapPin className="w-6 h-6 text-sky-400" /> 회원-거점 커버리지
          </h1>
          <p className="text-sm text-ink-400">
            페르소나 컨텍스트로 필터링된 회원의 시도별 분포를 한국 지도에 코로플레스로 그리고,
            같은 지도 위에 Warehouse 마커를 겹쳐 "내 페르소나 회원 중 N km 안에 거점이 없는 비율"을 한눈에 보여줍니다.
          </p>
        </div>

        {/* Controls — dimension toggle + radius slider */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-md border border-ink-700 bg-ink-900 overflow-hidden">
            {(Object.keys(DIM_LABEL) as Dim[]).map((d) => (
              <button
                key={d}
                onClick={() => setDim(d)}
                className={[
                  'px-3 py-1.5 text-xs font-semibold transition',
                  dim === d
                    ? 'bg-sky-500/15 text-sky-200'
                    : 'text-ink-300 hover:bg-ink-800',
                ].join(' ')}
              >
                {DIM_LABEL[d]}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs text-ink-300">
            <Compass className="w-3.5 h-3.5 text-sky-400" />
            도달 반경
            <input
              type="range"
              min={20}
              max={200}
              step={10}
              value={radius}
              onChange={(e) => setRadius(parseInt(e.target.value, 10))}
              className="w-32 accent-sky-400"
            />
            <span className="font-mono text-ink-100 w-12 text-right">{radius} km</span>
          </label>
          {active && (
            <span className="text-xs text-ink-400">
              페르소나: <span className="text-sky-300 font-semibold">{active.label}</span>
            </span>
          )}
        </div>

        {/* KPI strip — 4 cards */}
        {data && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            <KpiCard
              icon={Users}
              label={active ? `${active.label} 회원` : '전체 회원'}
              value={data.summary.total_members.toLocaleString()}
              sub={`region_id 부여된 회원 기준`}
              tone="cyan"
            />
            <KpiCard
              icon={Activity}
              label="도달 반경 내 회원 비율"
              value={`${data.summary.coverage_pct}%`}
              sub={`${data.summary.covered_members.toLocaleString()} / ${data.summary.total_members.toLocaleString()}`}
              tone={data.summary.coverage_pct >= 80 ? 'emerald' : 'amber'}
            />
            <KpiCard
              icon={AlertTriangle}
              label="미도달 회원"
              value={data.summary.uncovered_members.toLocaleString()}
              sub={`${radius} km 안에 거점 없음`}
              tone="rose"
            />
            <KpiCard
              icon={MapPin}
              label="Top 미도달 시도"
              value={data.summary.top_uncovered_region_ko ?? '없음'}
              sub={
                data.summary.top_uncovered_region_ko
                  ? `${data.summary.top_uncovered_member_count}명 미도달`
                  : '모든 시도 도달'
              }
              tone="rose"
            />
          </div>
        )}

        {error && (
          <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            {error}
          </div>
        )}

        {/* Map + side panel */}
        <div className="grid xl:grid-cols-[minmax(0,1fr)_360px] gap-5 min-h-0">
          <section className="rounded-lg border border-ink-700 bg-ink-900 p-3 min-h-[720px]">
            {loading ? (
              <div className="h-[720px] flex items-center justify-center text-xs text-ink-400">
                로딩 중…
              </div>
            ) : (
              <KoreaMapView
                markers={markers}
                regionFills={fills}
                selectedRegionCode={selectedRegion}
                onRegionClick={(code) => setSelectedRegion(code)}
                showLanes={false}
                height={760}
              />
            )}
          </section>

          <aside className="rounded-lg border border-ink-700 bg-ink-900 flex flex-col min-h-[720px] xl:min-h-0 overflow-hidden">
            <div className="px-3 py-2.5 border-b border-ink-700 text-xs uppercase tracking-wider text-ink-400 font-semibold">
              {selected ? `${selected.name_ko} 상세` : '시도 상세'}
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-4">
              {selected ? (
                <RegionDetail r={selected} />
              ) : (
                <p className="text-xs text-ink-400 leading-relaxed">
                  지도에서 시도를 클릭하면 회원·tier 분포와 가장 가까운 거점 정보가 여기 표시됩니다.
                </p>
              )}

              {uncoveredTopN.length > 0 && (
                <section>
                  <h3 className="text-[11px] uppercase tracking-wider text-ink-400 font-semibold mb-2">
                    미도달 Top {uncoveredTopN.length}
                  </h3>
                  <ul className="space-y-1">
                    {uncoveredTopN.map((r) => (
                      <li
                        key={r.region_code}
                        className="flex items-center justify-between text-xs px-2 py-1.5 rounded bg-ink-800 hover:bg-ink-700 cursor-pointer"
                        onClick={() => setSelectedRegion(r.region_code)}
                      >
                        <span className="text-ink-100">{r.name_ko}</span>
                        <span className="font-mono text-rose-300">{r.members}명</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section>
                <h3 className="text-[11px] uppercase tracking-wider text-ink-400 font-semibold mb-2">거점 마커</h3>
                <ul className="grid grid-cols-2 gap-1 text-[11px]">
                  {Object.entries(WH_TYPE_LABEL).map(([t, label]) => (
                    <li key={t} className="flex items-center gap-1.5 text-ink-300">
                      <span className={[
                        'inline-block w-2.5 h-2.5 rounded-full',
                        t === 'mfr' ? 'bg-emerald-400'
                          : t === 'rdc' ? 'bg-cyan-400'
                          : t === '3pl' ? 'bg-amber-400'
                          : 'bg-violet-400',
                      ].join(' ')} />
                      {label}
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </aside>
        </div>

        <footer className="text-[11px] text-ink-500 italic">
          ※ 합성 데이터(deterministic). 회원의 region_id는 페르소나 편향 분포로 생성된 가상 위치입니다.
        </footer>
      </div>
    </div>
  );
}


// ─── Subcomponents ────────────────────────────────────────────────────────


function KpiCard({
  icon: Icon, label, value, sub, tone = 'cyan',
}: {
  icon: any;
  label: string;
  value: string;
  sub?: string;
  tone?: 'cyan' | 'emerald' | 'amber' | 'rose';
}) {
  const TONE: Record<string, string> = {
    cyan:    'text-cyan-300 bg-cyan-500/10 border-cyan-500/30',
    emerald: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30',
    amber:   'text-amber-300 bg-amber-500/10 border-amber-500/30',
    rose:    'text-rose-300 bg-rose-500/10 border-rose-500/30',
  };
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 px-3 py-2.5">
      <div className="flex items-center gap-2 mb-1">
        <span className={`inline-flex w-6 h-6 items-center justify-center rounded border ${TONE[tone]}`}>
          <Icon className="w-3.5 h-3.5" />
        </span>
        <span className="text-[11px] uppercase tracking-wider text-ink-400 font-semibold">{label}</span>
      </div>
      <div className="text-xl font-bold text-ink-50">{value}</div>
      {sub && <div className="text-[11px] text-ink-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function RegionDetail({ r }: { r: api.RegionCoverage }) {
  const total = Math.max(1, r.members);
  return (
    <section className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="회원 수" value={r.members.toLocaleString()} />
        <Stat
          label="도달 여부"
          value={r.covered ? '도달' : '미도달'}
          tone={r.covered ? 'emerald' : 'rose'}
        />
        <Stat label="평균 이탈위험" value={r.avg_churn_risk.toFixed(2)} />
        <Stat label="평균 LTV" value={formatKrw(r.avg_ltv_krw)} />
        <Stat
          label="가까운 거점 거리"
          value={r.nearest_warehouse_km != null ? `${r.nearest_warehouse_km} km` : '—'}
        />
        <Stat label="가까운 거점" value={r.nearest_warehouse_id ?? '—'} />
      </div>

      <div>
        <h4 className="text-[11px] uppercase tracking-wider text-ink-400 font-semibold mb-1.5">
          <Crown className="w-3 h-3 inline -mt-0.5" /> Tier 믹스
        </h4>
        <ul className="space-y-1">
          {(['VIP', 'Gold', 'Silver', 'Bronze'] as const).map((t) => {
            const n = r.tier_mix[t] ?? 0;
            const pct = (n / total) * 100;
            return (
              <li key={t} className="text-[11px] text-ink-300">
                <div className="flex justify-between mb-0.5">
                  <span>{t}</span>
                  <span className="font-mono">{n} ({pct.toFixed(0)}%)</span>
                </div>
                <div className="h-1 bg-ink-800 rounded">
                  <div
                    className={[
                      'h-1 rounded',
                      t === 'VIP' ? 'bg-violet-400'
                        : t === 'Gold' ? 'bg-amber-400'
                        : t === 'Silver' ? 'bg-slate-300'
                        : 'bg-orange-700',
                    ].join(' ')}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

function Stat({
  label, value, tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'emerald' | 'rose';
}) {
  const TONE: Record<string, string> = {
    default: 'text-ink-100',
    emerald: 'text-emerald-300',
    rose: 'text-rose-300',
  };
  return (
    <div className="rounded bg-ink-800 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-ink-400">{label}</div>
      <div className={`text-sm font-semibold ${TONE[tone]}`}>{value}</div>
    </div>
  );
}
