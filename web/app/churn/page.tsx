'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import {
  TrendingDown, AlertTriangle, Megaphone, Crown, UserCircle, Sparkles,
  MapPin, BarChart3,
} from 'lucide-react';

import * as api from '@/lib/api-client';
import { KoreaMapView, RegionFill } from '@/components/map/KoreaMapView';
import { useActivePersona } from '@/lib/persona-context';

type ChurnTab = 'dashboard' | 'map';

const CytoscapeView = dynamic(
  () => import('@/components/graph/CytoscapeView').then((m) => m.CytoscapeView),
  { ssr: false },
);

// Tier badge palette — keeps the dashboard cards visually consistent with
// the membership color identity used across Sidebar / Object Explorer.
const TIER_PALETTE: Record<string, { bg: string; text: string; border: string }> = {
  VIP:    { bg: 'bg-yellow-500/15', text: 'text-yellow-300', border: 'border-yellow-500/40' },
  Gold:   { bg: 'bg-amber-500/15',  text: 'text-amber-300',  border: 'border-amber-500/40' },
  Silver: { bg: 'bg-slate-400/15',  text: 'text-slate-200',  border: 'border-slate-400/40' },
  Bronze: { bg: 'bg-orange-700/20', text: 'text-orange-200', border: 'border-orange-600/40' },
};

function fmtKrw(v: number): string {
  if (v >= 10_000_000) return `${(v / 10_000_000).toFixed(1)}천만`;
  if (v >= 10_000) return `${(v / 10_000).toFixed(0)}만`;
  return v.toLocaleString();
}

function riskTone(risk: number): string {
  if (risk >= 0.7) return 'text-rose-300';
  if (risk >= 0.4) return 'text-amber-300';
  return 'text-emerald-300';
}

export default function ChurnPage() {
  const { active } = useActivePersona();
  const [tab, setTab] = useState<ChurnTab>('dashboard');
  const [data, setData] = useState<api.ChurnDashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<api.ChurnMemberDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [mapData, setMapData] = useState<api.ChurnMapResponse | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.churnDashboard(30)
      .then((d) => { if (!cancelled) { setData(d); if (d.top_at_risk[0]) setSelectedId(d.top_at_risk[0].member_id); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'dashboard failed'); });
    return () => { cancelled = true; };
  }, []);

  // 지도 탭 진입 시 또는 페르소나 변경 시 churn map 데이터 (re-)fetch.
  useEffect(() => {
    if (tab !== 'map') return;
    let cancelled = false;
    api.churnMap(active?.id ?? null)
      .then((d) => { if (!cancelled) setMapData(d); })
      .catch(() => { /* keep prior data on error */ });
    return () => { cancelled = true; };
  }, [tab, active?.id]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    let cancelled = false;
    setDetailLoading(true); setDetail(null);
    api.churnMember(selectedId)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch(() => { /* keep dashboard subgraph as fallback */ })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId]);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 border-b border-ink-700 bg-ink-900 flex items-center px-6">
        <div className="text-xs text-ink-400">시나리오 I · 이탈 위험 진단</div>
        <span className="ml-3 text-[10px] font-mono px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-300 border border-orange-500/30">
          Member × Touchpoint × RFM → winback 추천
        </span>
      </header>

      <div className="flex-1 px-6 py-6 max-w-[1500px] mx-auto w-full flex flex-col gap-5">
        <div>
          <h1 className="text-2xl font-bold text-ink-50 mb-1 flex items-center gap-2">
            <TrendingDown className="w-6 h-6 text-orange-400" /> 이탈 위험 진단
          </h1>
          <p className="text-sm text-ink-400">
            VIP/고가치 회원 중 90일 미접속 + 캠페인 미응답자를 식별하고, 페르소나별 분포와 winback 캠페인을 추천합니다.
            합성 1,000명 회원 데이터에 RFM(Recency·Frequency·Monetary) 기반 churn_risk가 적재되어 있습니다.
          </p>
        </div>

        {error && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
            {error}
          </div>
        )}

        {/* KPI strip */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard icon={UserCircle} label="총 회원" value={data?.summary.total_members ?? '—'} accent="text-orange-300" />
          <KpiCard
            icon={AlertTriangle}
            label="고위험 (≥0.7)"
            value={data ? `${data.summary.high_risk_count} (${(data.summary.high_risk_pct * 100).toFixed(1)}%)` : '—'}
            accent="text-rose-300"
          />
          <KpiCard icon={Crown} label="VIP 이탈 위험" value={data?.summary.vip_at_risk_count ?? '—'} accent="text-yellow-300" />
          <KpiCard icon={TrendingDown} label="평균 미접속(일)" value={data?.summary.avg_recency_days ?? '—'} accent="text-amber-300" />
        </section>

        {/* Tab strip — 대시보드 / 지도 */}
        <div className="flex border-b border-ink-700 -mb-1">
          <TabBtn active={tab === 'dashboard'} onClick={() => setTab('dashboard')} icon={BarChart3} label="대시보드" />
          <TabBtn active={tab === 'map'} onClick={() => setTab('map')} icon={MapPin} label="지도" />
        </div>

        {tab === 'map' ? (
          <ChurnMapView
            data={mapData}
            persona={active}
            selectedRegion={selectedRegion}
            onSelectRegion={setSelectedRegion}
          />
        ) : (
        /* Workspace */
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Left column: breakdowns + winback */}
          <div className="flex flex-col gap-4">
            <Card title="회원 등급별 위험 분포">
              <table className="w-full text-sm">
                <thead className="text-xs text-ink-400">
                  <tr>
                    <th className="text-left py-1.5">등급</th>
                    <th className="text-right py-1.5">총원</th>
                    <th className="text-right py-1.5">고위험</th>
                    <th className="text-right py-1.5">평균 risk</th>
                    <th className="text-right py-1.5">평균 LTV</th>
                  </tr>
                </thead>
                <tbody className="text-ink-200">
                  {data?.tier_breakdown.map((t) => (
                    <tr key={t.tier} className="border-t border-ink-700/60">
                      <td className="py-1.5">
                        <TierBadge tier={t.tier} />
                      </td>
                      <td className="text-right">{t.total}</td>
                      <td className={`text-right font-medium ${t.at_risk > 0 ? 'text-rose-300' : 'text-ink-300'}`}>{t.at_risk}</td>
                      <td className={`text-right ${riskTone(t.avg_churn_risk)}`}>{t.avg_churn_risk.toFixed(2)}</td>
                      <td className="text-right text-ink-300">{fmtKrw(t.avg_ltv_krw)}원</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card title="페르소나별 위험 분포">
              <table className="w-full text-sm">
                <thead className="text-xs text-ink-400">
                  <tr>
                    <th className="text-left py-1.5">페르소나</th>
                    <th className="text-right py-1.5">총원</th>
                    <th className="text-right py-1.5">고위험</th>
                    <th className="text-right py-1.5">평균 risk</th>
                  </tr>
                </thead>
                <tbody className="text-ink-200">
                  {data?.persona_breakdown.map((p) => (
                    <tr key={p.persona_id} className="border-t border-ink-700/60">
                      <td className="py-1.5">{p.persona_label_ko || p.persona_id}</td>
                      <td className="text-right">{p.total}</td>
                      <td className={`text-right font-medium ${p.at_risk > 0 ? 'text-rose-300' : 'text-ink-300'}`}>{p.at_risk}</td>
                      <td className={`text-right ${riskTone(p.avg_churn_risk)}`}>{p.avg_churn_risk.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card title="추천 Winback 캠페인" icon={Megaphone}>
              {data?.recommended_winback.length ? (
                <ul className="flex flex-col gap-2">
                  {data.recommended_winback.map((c) => (
                    <li key={c.campaign_id} className="rounded-md border border-ink-700 bg-ink-900 p-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-ink-100">{c.name_ko}</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-fuchsia-500/15 text-fuchsia-300 border border-fuchsia-500/30">
                          {c.channel}
                        </span>
                      </div>
                      <div className="text-xs text-ink-400 mt-1">
                        예상 응답률 {(c.expected_response_rate * 100).toFixed(0)}%
                        {c.target_persona_ids.length > 0 && (
                          <span className="ml-2">· 대상 페르소나 {c.target_persona_ids.join(', ')}</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <div className="text-sm text-ink-400">winback 캠페인 없음</div>}
            </Card>
          </div>

          {/* Right column: top at-risk list + selected member detail */}
          <div className="flex flex-col gap-4">
            <Card title={`이탈 위험 상위 ${data?.top_at_risk.length ?? 0}명`}>
              <div className="max-h-72 overflow-y-auto -mx-1">
                <table className="w-full text-sm">
                  <thead className="text-xs text-ink-400 sticky top-0 bg-ink-800">
                    <tr>
                      <th className="text-left px-2 py-1.5">회원</th>
                      <th className="text-left px-2 py-1.5">등급</th>
                      <th className="text-right px-2 py-1.5">risk</th>
                      <th className="text-right px-2 py-1.5">미접속</th>
                      <th className="text-right px-2 py-1.5">LTV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.top_at_risk.map((m) => {
                      const active = selectedId === m.member_id;
                      return (
                        <tr
                          key={m.member_id}
                          onClick={() => setSelectedId(m.member_id)}
                          className={`cursor-pointer border-t border-ink-700/60 ${active ? 'bg-orange-500/10' : 'hover:bg-ink-700/40'}`}
                        >
                          <td className="px-2 py-1.5">
                            <div className="font-medium text-ink-100">{m.name_ko}</div>
                            <div className="text-[10px] text-ink-500 font-mono">{m.member_id}</div>
                          </td>
                          <td className="px-2 py-1.5"><TierBadge tier={m.tier} /></td>
                          <td className={`text-right px-2 py-1.5 font-mono ${riskTone(m.churn_risk)}`}>{m.churn_risk.toFixed(2)}</td>
                          <td className="text-right px-2 py-1.5 text-ink-300">{m.recency_days}일</td>
                          <td className="text-right px-2 py-1.5 text-ink-300">{fmtKrw(m.ltv_krw)}원</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title={detail ? `${detail.member.name_ko} (${detail.member.member_id}) — 1-hop 그래프` : '회원 1-hop 그래프'}>
              <CytoscapeView
                subgraph={detail?.subgraph ?? data?.subgraph ?? { nodes: [], edges: [] }}
                wowNodeIds={selectedId ? [`mem_${selectedId.replace('mem_', '')}`] : []}
                height={320}
              />
              {detail && (
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-md border border-ink-700 bg-ink-900 p-2">
                    <div className="text-ink-400">최근 거래 ({detail.transactions.length}건)</div>
                    {detail.transactions.slice(0, 3).map((t) => (
                      <div key={t.transaction_id} className="text-ink-200 mt-0.5 truncate">
                        {t.ts} · {fmtKrw(t.amount_krw)}원 · {t.product_name_ko ?? t.sku_id ?? '—'}
                      </div>
                    ))}
                    {detail.transactions.length === 0 && <div className="text-ink-500 mt-0.5">거래 없음</div>}
                  </div>
                  <div className="rounded-md border border-ink-700 bg-ink-900 p-2">
                    <div className="text-ink-400">캠페인 응답률 {(detail.response_rate * 100).toFixed(0)}%</div>
                    {detail.recommended_campaign && (
                      <div className="mt-0.5 flex items-center gap-1 flex-wrap">
                        <Sparkles className="w-3 h-3 text-fuchsia-300" />
                        <span className="text-ink-200">추천:</span>
                        <span className="text-fuchsia-200">{detail.recommended_campaign.name_ko}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {detailLoading && <div className="mt-2 text-xs text-ink-400">상세 로딩 중…</div>}
            </Card>
          </div>
        </section>
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
          ? 'border-orange-400 text-orange-200 bg-orange-500/5'
          : 'border-transparent text-ink-400 hover:text-ink-200 hover:bg-ink-800/50',
      ].join(' ')}
    >
      <Icon className="w-3.5 h-3.5" />
      {label}
    </button>
  );
}

function ChurnMapView({
  data, persona, selectedRegion, onSelectRegion,
}: {
  data: api.ChurnMapResponse | null;
  persona: { id: string; label: string } | null;
  selectedRegion: string | null;
  onSelectRegion: (code: string | null) => void;
}) {
  // avg_churn_risk 의 max 로 정규화 — 색이 항상 의미 있게 분포하도록.
  const fills: RegionFill[] = useMemo(() => {
    if (!data) return [];
    const max = Math.max(...data.regions.map((r) => r.avg_churn_risk), 1e-9);
    return data.regions.map((r) => ({
      region_code: r.region_code,
      value: r.avg_churn_risk / max,
      hue: 'rose',
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
          <span>{selected ? `${selected.name_ko} 상세` : '시도별 이탈 위험'}</span>
          {persona && (
            <span className="text-[10px] text-orange-300 normal-case">
              {persona.label} 슬라이스
            </span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {selected ? (
            <div className="grid grid-cols-2 gap-2">
              <Stat label="회원 수" value={selected.members.toLocaleString()} />
              <Stat
                label="고위험 (≥0.7)"
                value={`${selected.at_risk} (${((selected.at_risk / Math.max(1, selected.members)) * 100).toFixed(0)}%)`}
                tone="rose"
              />
              <Stat label="평균 risk" value={selected.avg_churn_risk.toFixed(2)} />
              <Stat label="평균 LTV" value={fmtKrw(selected.avg_ltv_krw) + '원'} />
            </div>
          ) : (
            <p className="text-xs text-ink-400 leading-relaxed">
              지도에서 시도를 클릭하면 해당 지역의 회원 수·고위험 비율·평균 LTV가 표시됩니다.
              {persona && ` 현재 ${persona.label} 페르소나 슬라이스만 집계.`}
            </p>
          )}

          <section>
            <h3 className="text-[11px] uppercase tracking-wider text-ink-400 font-semibold mb-2">
              평균 이탈 위험 Top {Math.min(5, data?.regions.length ?? 0)}
            </h3>
            <ul className="space-y-1">
              {(data?.regions ?? [])
                .filter((r) => r.members > 0)
                .sort((a, b) => b.avg_churn_risk - a.avg_churn_risk)
                .slice(0, 5)
                .map((r) => (
                  <li
                    key={r.region_code}
                    onClick={() => onSelectRegion(r.region_code)}
                    className="flex items-center justify-between text-xs px-2 py-1.5 rounded bg-ink-800 hover:bg-ink-700 cursor-pointer"
                  >
                    <span className="text-ink-100">{r.name_ko || r.region_code}</span>
                    <span className={`font-mono ${r.avg_churn_risk >= 0.5 ? 'text-rose-300' : 'text-amber-300'}`}>
                      {r.avg_churn_risk.toFixed(2)} · {r.at_risk}/{r.members}
                    </span>
                  </li>
                ))}
            </ul>
          </section>

          <p className="text-[10px] text-ink-500 italic">
            ※ Member.region_id 가 부여된 회원만 집계. 임계값 risk ≥ {(data?.high_risk_threshold ?? 0.7).toFixed(2)}.
          </p>
        </div>
      </aside>
    </div>
  );
}

function Stat({ label, value, tone = 'default' }: {
  label: string;
  value: string;
  tone?: 'default' | 'rose';
}) {
  const TONE: Record<string, string> = {
    default: 'text-ink-100',
    rose: 'text-rose-300',
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
        {Icon && <Icon className="w-4 h-4 text-orange-300" />}
        <h2 className="text-sm font-semibold text-ink-100">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function TierBadge({ tier }: { tier: string }) {
  const c = TIER_PALETTE[tier] ?? TIER_PALETTE.Bronze;
  return (
    <span className={`inline-block text-[10px] font-mono px-1.5 py-0.5 rounded border ${c.bg} ${c.text} ${c.border}`}>
      {tier}
    </span>
  );
}
