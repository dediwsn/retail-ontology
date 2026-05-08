'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ArrowUpRight, Crown, Layers, Users, Sparkles, MapPin, BarChart3,
} from 'lucide-react';

import * as api from '@/lib/api-client';
import { KoreaMapView, RegionFill } from '@/components/map/KoreaMapView';
import { useActivePersona } from '@/lib/persona-context';

type TierUpTab = 'dashboard' | 'map';

function fmtKrw(v: number): string {
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}억`;
  if (v >= 10_000_000) return `${(v / 10_000_000).toFixed(1)}천만`;
  if (v >= 10_000) return `${(v / 10_000).toFixed(0)}만`;
  return v.toLocaleString();
}

function liftTone(lift: number): string {
  if (lift >= 2) return 'text-emerald-300';
  if (lift >= 1.3) return 'text-amber-300';
  return 'text-ink-300';
}

// Bar width proportional to lift, capped so super-outliers don't crowd out.
function liftBarWidth(lift: number, maxLift: number): string {
  if (maxLift <= 0) return '0%';
  return `${Math.min(100, (lift / maxLift) * 100).toFixed(1)}%`;
}

export default function TierUpPage() {
  const { active } = useActivePersona();
  const [tab, setTab] = useState<TierUpTab>('dashboard');
  const [data, setData] = useState<api.TierUpDashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mapData, setMapData] = useState<api.TierUpMapResponse | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.tierUpDashboard(25)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'load failed'); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (tab !== 'map') return;
    let cancelled = false;
    api.tierUpMap(active?.id ?? null)
      .then((d) => { if (!cancelled) setMapData(d); })
      .catch(() => { /* keep prior data on error */ });
    return () => { cancelled = true; };
  }, [tab, active?.id]);

  const maxProductLift = data?.product_lift[0]?.lift ?? 1;
  const maxCategoryLift = data?.category_lift[0]?.lift ?? 1;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 border-b border-ink-700 bg-ink-900 flex items-center px-6">
        <div className="text-xs text-ink-400">시나리오 K · 등급 상승 경로</div>
        <span className="ml-3 text-[10px] font-mono px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-300 border border-yellow-500/30">
          Silver vs Gold lift → 등급 상승 시그널 + 업그레이드 후보
        </span>
      </header>

      <div className="flex-1 px-6 py-6 max-w-[1500px] mx-auto w-full flex flex-col gap-5">
        <div>
          <h1 className="text-2xl font-bold text-ink-50 mb-1 flex items-center gap-2">
            <ArrowUpRight className="w-6 h-6 text-yellow-400" /> 등급 상승 경로
          </h1>
          <p className="text-sm text-ink-400">
            Gold 회원이 Silver 회원 대비 더 많이 구매하는 카테고리·상품을 lift로 비교하여 "등급 상승 시그널"을 식별합니다.
            동시에 LTV 1.5M~2M 사이 Silver 회원을 "업그레이드 후보"로 추출합니다.
          </p>
        </div>

        {error && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
            {error}
          </div>
        )}

        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard icon={Users} label="Silver 회원" value={data?.summary.silver_count ?? '—'} accent="text-slate-200" />
          <KpiCard icon={Crown} label="Gold 회원" value={data?.summary.gold_count ?? '—'} accent="text-amber-300" />
          <KpiCard
            icon={ArrowUpRight}
            label="업그레이드 후보"
            value={data?.summary.candidates_count ?? '—'}
            accent="text-yellow-300"
          />
          <KpiCard
            icon={Sparkles}
            label="후보 평균 LTV"
            value={data ? `${fmtKrw(data.summary.avg_candidate_ltv_krw)}원` : '—'}
            accent="text-emerald-300"
          />
        </section>

        {/* Tab strip — 대시보드 / 지도 */}
        <div className="flex border-b border-ink-700 -mb-1">
          <TabBtn active={tab === 'dashboard'} onClick={() => setTab('dashboard')} icon={BarChart3} label="대시보드" />
          <TabBtn active={tab === 'map'} onClick={() => setTab('map')} icon={MapPin} label="지도" />
        </div>

        {tab === 'map' ? (
          <TierUpMapView
            data={mapData}
            persona={active}
            selectedRegion={selectedRegion}
            onSelectRegion={setSelectedRegion}
          />
        ) : (
        <>
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Category lift */}
          <Card title="카테고리별 Silver→Gold lift" icon={Layers}>
            <ul className="flex flex-col gap-1.5">
              {data?.category_lift.map((c) => (
                <li key={c.gs1_brick_code} className="flex items-center gap-2 text-sm">
                  <div className="w-32 truncate text-ink-100" title={c.name_ko}>{c.name_ko || c.gs1_brick_code}</div>
                  <div className="flex-1 h-2 rounded bg-ink-700/50 overflow-hidden">
                    <div
                      className="h-full bg-yellow-400/70"
                      style={{ width: liftBarWidth(c.lift, maxCategoryLift) }}
                    />
                  </div>
                  <div className={`w-12 text-right font-mono text-xs ${liftTone(c.lift)}`}>{c.lift.toFixed(2)}×</div>
                  <div className="w-20 text-right text-[10px] text-ink-500 font-mono">
                    G{c.gold_buyers}/S{c.silver_buyers}
                  </div>
                </li>
              ))}
              {!data?.category_lift.length && <li className="text-sm text-ink-400">데이터 없음</li>}
            </ul>
          </Card>

          {/* Product lift */}
          <Card title="상품별 Silver→Gold lift (top 25)">
            <div className="max-h-96 overflow-y-auto -mx-1">
              <ul className="flex flex-col gap-1.5 px-1">
                {data?.product_lift.map((p) => (
                  <li key={p.sku_id} className="flex items-center gap-2 text-sm">
                    <div className="w-44 truncate text-ink-100" title={p.name_ko}>{p.name_ko || p.sku_id}</div>
                    <div className="flex-1 h-2 rounded bg-ink-700/50 overflow-hidden">
                      <div
                        className="h-full bg-yellow-400/70"
                        style={{ width: liftBarWidth(p.lift, maxProductLift) }}
                      />
                    </div>
                    <div className={`w-12 text-right font-mono text-xs ${liftTone(p.lift)}`}>{p.lift.toFixed(2)}×</div>
                    {p.domain && (
                      <span className="w-12 text-right text-[10px] text-ink-500 font-mono">{p.domain === 'beauty' ? '뷰티' : '식품'}</span>
                    )}
                  </li>
                ))}
                {!data?.product_lift.length && <li className="text-sm text-ink-400">데이터 없음</li>}
              </ul>
            </div>
          </Card>
        </section>

        {/* Upgrade candidates */}
        <Card title={`업그레이드 후보 (Silver, LTV ≥ 1.5M)`}>
          <div className="max-h-80 overflow-y-auto -mx-1">
            <table className="w-full text-sm">
              <thead className="text-xs text-ink-400 sticky top-0 bg-ink-800">
                <tr>
                  <th className="text-left px-2 py-1.5">회원</th>
                  <th className="text-left px-2 py-1.5">페르소나</th>
                  <th className="text-right px-2 py-1.5">LTV</th>
                  <th className="text-right px-2 py-1.5">Gold까지</th>
                  <th className="text-right px-2 py-1.5">Frequency</th>
                  <th className="text-right px-2 py-1.5">미접속</th>
                  <th className="text-right px-2 py-1.5">churn risk</th>
                </tr>
              </thead>
              <tbody>
                {data?.upgrade_candidates.map((m) => {
                  const riskTone =
                    m.churn_risk >= 0.7 ? 'text-rose-300'
                    : m.churn_risk >= 0.4 ? 'text-amber-300'
                    : 'text-emerald-300';
                  return (
                    <tr key={m.member_id} className="border-t border-ink-700/60 hover:bg-ink-700/30">
                      <td className="px-2 py-1.5">
                        <div className="text-ink-100">{m.name_ko}</div>
                        <div className="text-[10px] text-ink-500 font-mono">{m.member_id}</div>
                      </td>
                      <td className="px-2 py-1.5 text-ink-200">{m.persona_label_ko || m.persona_id || '—'}</td>
                      <td className="text-right px-2 py-1.5 text-ink-200">{fmtKrw(m.ltv_krw)}원</td>
                      <td className="text-right px-2 py-1.5 text-yellow-300">{fmtKrw(m.gap_to_gold_krw)}원</td>
                      <td className="text-right px-2 py-1.5 text-ink-200">{m.frequency}회</td>
                      <td className="text-right px-2 py-1.5 text-ink-300">{m.recency_days}일</td>
                      <td className={`text-right px-2 py-1.5 font-mono ${riskTone}`}>{m.churn_risk.toFixed(2)}</td>
                    </tr>
                  );
                })}
                {!data?.upgrade_candidates.length && (
                  <tr><td colSpan={7} className="text-center py-3 text-ink-400">후보 없음</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
        </>
        )}
      </div>
    </div>
  );
}

function TabBtn({
  active, onClick, icon: Icon, label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'px-4 py-2 text-xs font-semibold flex items-center gap-1.5 transition border-b-2 -mb-px',
        active
          ? 'border-yellow-400 text-yellow-200 bg-yellow-500/5'
          : 'border-transparent text-ink-400 hover:text-ink-200 hover:bg-ink-800/50',
      ].join(' ')}
    >
      <Icon className="w-3.5 h-3.5" />
      {label}
    </button>
  );
}

function TierUpMapView({
  data, persona, selectedRegion, onSelectRegion,
}: {
  data: api.TierUpMapResponse | null;
  persona: { id: string; label: string } | null;
  selectedRegion: string | null;
  onSelectRegion: (code: string | null) => void;
}) {
  // 코로플레스 색은 candidate_count 정규화 — 업그레이드 가능성이 큰 지역이 진하게.
  const fills: RegionFill[] = useMemo(() => {
    if (!data) return [];
    const max = Math.max(...data.regions.map((r) => r.candidate_count), 1);
    return data.regions.map((r) => ({
      region_code: r.region_code,
      value: r.candidate_count / max,
      hue: 'amber',
    }));
  }, [data]);

  const selected = useMemo(
    () => (selectedRegion ? data?.regions.find((r) => r.region_code === selectedRegion) : null),
    [data, selectedRegion],
  );

  return (
    <div className="grid xl:grid-cols-[minmax(0,1fr)_320px] gap-5">
      <section className="rounded-lg border border-ink-700 bg-ink-900 p-3 min-h-[700px]">
        {!data ? (
          <div className="h-[700px] flex items-center justify-center text-xs text-ink-400">로딩 중…</div>
        ) : (
          <KoreaMapView
            regionFills={fills}
            selectedRegionCode={selectedRegion}
            onRegionClick={(code) => onSelectRegion(code)}
            showLanes={false}
            height={760}
          />
        )}
      </section>

      <aside className="rounded-lg border border-ink-700 bg-ink-900 flex flex-col min-h-[700px] overflow-hidden">
        <div className="px-3 py-2.5 border-b border-ink-700 text-xs uppercase tracking-wider text-ink-400 font-semibold flex items-center justify-between">
          <span>{selected ? `${selected.name_ko} 상세` : '시도별 업그레이드 후보'}</span>
          {persona && (
            <span className="text-[10px] text-yellow-300 normal-case">
              {persona.label} 슬라이스
            </span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {selected ? (
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Silver 회원" value={selected.silver_count.toLocaleString()} />
              <Stat label="Gold 회원" value={selected.gold_count.toLocaleString()} tone="amber" />
              <Stat
                label="업그레이드 후보"
                value={selected.candidate_count.toLocaleString()}
                tone="amber"
              />
              <Stat label="Silver 평균 LTV" value={fmtKrw(selected.avg_silver_ltv_krw) + '원'} />
              <Stat label="Gold까지 평균 갭" value={fmtKrw(selected.avg_gap_to_gold_krw) + '원'} />
            </div>
          ) : (
            <p className="text-xs text-ink-400 leading-relaxed">
              지도에서 시도를 클릭하면 Silver/Gold 분포와 업그레이드 후보 수가 표시됩니다.
              {persona && ` 현재 ${persona.label} 페르소나 슬라이스만 집계.`}
            </p>
          )}

          <section>
            <h3 className="text-[11px] uppercase tracking-wider text-ink-400 font-semibold mb-2">
              업그레이드 후보 Top {Math.min(5, data?.regions.length ?? 0)}
            </h3>
            <ul className="space-y-1">
              {(data?.regions ?? [])
                .filter((r) => r.candidate_count > 0)
                .sort((a, b) => b.candidate_count - a.candidate_count)
                .slice(0, 5)
                .map((r) => (
                  <li
                    key={r.region_code}
                    onClick={() => onSelectRegion(r.region_code)}
                    className="flex items-center justify-between text-xs px-2 py-1.5 rounded bg-ink-800 hover:bg-ink-700 cursor-pointer"
                  >
                    <span className="text-ink-100">{r.name_ko || r.region_code}</span>
                    <span className="font-mono text-yellow-300">{r.candidate_count}명</span>
                  </li>
                ))}
            </ul>
          </section>

          <p className="text-[10px] text-ink-500 italic">
            ※ 후보 = Silver tier 중 LTV ≥ {fmtKrw(data?.candidate_ltv_floor_krw ?? 1_500_000)}원.
            Gold 임계 {fmtKrw(data?.gold_threshold_krw ?? 2_000_000)}원.
          </p>
        </div>
      </aside>
    </div>
  );
}

function Stat({ label, value, tone = 'default' }: {
  label: string;
  value: string;
  tone?: 'default' | 'amber';
}) {
  const TONE: Record<string, string> = {
    default: 'text-ink-100',
    amber: 'text-amber-300',
  };
  return (
    <div className="rounded bg-ink-800 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-ink-400">{label}</div>
      <div className={`text-sm font-semibold ${TONE[tone]}`}>{value}</div>
    </div>
  );
}

function KpiCard({
  icon: Icon, label, value, accent,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | string;
  accent: string;
}) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-800 px-4 py-3">
      <div className="flex items-center gap-1.5 text-xs text-ink-400">
        <Icon className={`w-3.5 h-3.5 ${accent}`} /> {label}
      </div>
      <div className={`mt-1 text-xl font-semibold ${accent}`}>{value}</div>
    </div>
  );
}

function Card({
  title, icon: Icon, children,
}: {
  title: string;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-800 p-4">
      <div className="flex items-center gap-2 mb-3">
        {Icon && <Icon className="w-4 h-4 text-yellow-300" />}
        <h2 className="text-sm font-semibold text-ink-100">{title}</h2>
      </div>
      {children}
    </div>
  );
}
