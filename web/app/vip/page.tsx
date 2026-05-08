'use client';

// Scenario M — VIP Target Builder.
//
// Surfaces the wallet-share-aware "Opportunity VIP" cohort: members who
// spend big externally in some category but where we capture <30% of
// their wallet. These are the highest-ROI growth targets that internal
// data alone cannot identify.
//
// Page structure: tab strip with 5 VIP definitions (Opportunity = full,
// the other 4 are stubs flagged "다음 반복" — same data layer, just a
// different Cypher each).
//
// Color identity: violet (next free tone after lime/L). Persona context
// is honoured via the global PersonaSwitch.

import { useEffect, useMemo, useState } from 'react';
import {
  Wallet, AlertTriangle, TrendingUp, Crown, Sparkles, Target,
  ArrowUpRight, Lock, Layers,
} from 'lucide-react';

import * as api from '@/lib/api-client';
import { useActivePersona } from '@/lib/persona-context';

type VipTab = 'opportunity' | 'loyal' | 'whale' | 'cross_category' | 'trajectory';

const TAB_META: Record<VipTab, {
  ko: string; icon: any; ready: boolean; oneLiner: string;
}> = {
  opportunity:    { ko: '기회 VIP',     icon: Target,       ready: true,
                    oneLiner: '큰 카테고리 지출 + 우리 점유율 < 30% — 가장 큰 성장 가능성' },
  loyal:          { ko: '충성 VIP',     icon: Crown,        ready: false,
                    oneLiner: '우리 점유율 ≥ 70% + 카테고리 총액 ≥ 1M — 가격 보호·VIP 컨시어지' },
  whale:          { ko: '내부 Whale',   icon: Wallet,       ready: false,
                    oneLiner: 'tier=VIP 직접 분류 — 기존 정의' },
  cross_category: { ko: '인접 카테고리', icon: Layers,       ready: false,
                    oneLiner: '우리에게 한 카테고리만 사고 인접 외부 카테고리 큰 지출 — Up-sell' },
  trajectory:     { ko: '잠재 VIP',     icon: TrendingUp,   ready: false,
                    oneLiner: '내부·외부 지출 추세 ↑ — 잠재 VIP, 캠페인 우선 노출' },
};

function fmtKrw(v: number): string {
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}억원`;
  if (v >= 10_000_000) return `${(v / 10_000_000).toFixed(1)}천만원`;
  if (v >= 10_000) return `${(v / 10_000).toFixed(0)}만원`;
  return `${v.toLocaleString()}원`;
}

const TIER_PALETTE: Record<string, string> = {
  VIP:    'bg-yellow-500/15 text-yellow-300 border-yellow-500/40',
  Gold:   'bg-amber-500/15 text-amber-300 border-amber-500/40',
  Silver: 'bg-slate-400/15 text-slate-200 border-slate-400/40',
  Bronze: 'bg-orange-700/20 text-orange-200 border-orange-600/40',
};

export default function VipPage() {
  const { active } = useActivePersona();
  const [tab, setTab] = useState<VipTab>('opportunity');
  const [shareCeiling, setShareCeiling] = useState<number>(0.3);
  const [totalFloor, setTotalFloor] = useState<number>(500_000);
  const [data, setData] = useState<api.OpportunityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (tab !== 'opportunity') return;
    setLoading(true);
    setError(null);
    api.vipOpportunity({
      persona: active?.id ?? null,
      share_ceiling: shareCeiling,
      total_floor_krw: totalFloor,
      top_k: 50,
    })
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [tab, active?.id, shareCeiling, totalFloor]);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 border-b border-ink-700 bg-ink-900 flex items-center px-6">
        <div className="text-xs text-ink-400">시나리오 M · VIP 타깃 빌더 (외부 소비 데이터)</div>
        <span className="ml-3 text-[10px] font-mono px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300 border border-violet-500/30">
          멤버쉽 × IndustryCategory · wallet share 분석
        </span>
      </header>

      <div className="flex-1 px-6 py-6 max-w-[1500px] mx-auto w-full flex flex-col gap-5 min-h-0">
        <div>
          <h1 className="text-2xl font-bold text-ink-50 mb-1 flex items-center gap-2">
            <Target className="w-6 h-6 text-violet-400" /> VIP 타깃 빌더
          </h1>
          <p className="text-sm text-ink-400">
            외부 소비 패널 데이터(NICE/마이데이터 스타일) 를 멤버쉽 위에 얹어 *우리에게 보이지 않던* VIP를 식별합니다.
            동일 데이터 위에서 5가지 VIP 정의를 동시에 운용 — 정의가 바뀌어도 데이터를 재이전 안 함.
          </p>
        </div>

        {/* Tab strip */}
        <div className="flex border-b border-ink-700 -mb-1 overflow-x-auto">
          {(Object.keys(TAB_META) as VipTab[]).map((k) => {
            const meta = TAB_META[k];
            const Icon = meta.icon;
            const isActive = tab === k;
            return (
              <button
                key={k}
                onClick={() => setTab(k)}
                disabled={!meta.ready}
                title={meta.ready ? meta.oneLiner : `${meta.oneLiner} — 다음 반복에서 추가`}
                className={[
                  'px-4 py-2 text-xs font-semibold flex items-center gap-1.5 transition border-b-2 -mb-px whitespace-nowrap',
                  !meta.ready ? 'border-transparent text-ink-500 cursor-not-allowed opacity-60' :
                    isActive ? 'border-violet-400 text-violet-200 bg-violet-500/5'
                             : 'border-transparent text-ink-300 hover:text-ink-100 hover:bg-ink-800/50',
                ].join(' ')}
              >
                <Icon className="w-3.5 h-3.5" />
                {meta.ko}
                {!meta.ready && <Lock className="w-3 h-3 ml-0.5" />}
              </button>
            );
          })}
        </div>

        {tab === 'opportunity' ? (
          <>
            {/* Controls */}
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 text-xs text-ink-300">
                <span className="font-semibold">우리 점유율 ≤</span>
                <input
                  type="range"
                  min={0.05} max={0.7} step={0.05}
                  value={shareCeiling}
                  onChange={(e) => setShareCeiling(parseFloat(e.target.value))}
                  className="w-32 accent-violet-400"
                />
                <span className="font-mono text-ink-100 w-12 text-right">
                  {Math.round(shareCeiling * 100)}%
                </span>
              </label>
              <label className="flex items-center gap-2 text-xs text-ink-300">
                <span className="font-semibold">카테고리 총액 ≥</span>
                <input
                  type="range"
                  min={100_000} max={3_000_000} step={100_000}
                  value={totalFloor}
                  onChange={(e) => setTotalFloor(parseInt(e.target.value, 10))}
                  className="w-32 accent-violet-400"
                />
                <span className="font-mono text-ink-100 w-16 text-right">
                  {fmtKrw(totalFloor)}
                </span>
              </label>
              {active && (
                <span className="text-xs text-ink-400">
                  페르소나: <span className="text-violet-300 font-semibold">{active.label}</span>
                </span>
              )}
            </div>

            {/* KPI strip */}
            {data && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                <KpiCard
                  icon={Target}
                  label="기회 후보 (member × category)"
                  value={data.summary.candidate_count.toLocaleString()}
                  sub={`고유 회원 ${data.summary.distinct_member_count}명`}
                  tone="violet"
                />
                <KpiCard
                  icon={ArrowUpRight}
                  label="총 미점유 금액 (untapped)"
                  value={fmtKrw(data.summary.sum_untapped_krw)}
                  sub={`현재 우리 점유 평균 ${(data.summary.avg_our_share * 100).toFixed(1)}%`}
                  tone="emerald"
                />
                <KpiCard
                  icon={Sparkles}
                  label="최다 기회 카테고리"
                  value={data.summary.top_industry_ko ?? '없음'}
                  sub={data.summary.top_industry_id ?? ''}
                  tone="amber"
                />
                <KpiCard
                  icon={AlertTriangle}
                  label="필터 임계"
                  value={`점유율 ≤ ${Math.round(data.summary.share_ceiling * 100)}%`}
                  sub={`카테고리 총액 ≥ ${fmtKrw(data.summary.total_floor_krw)}`}
                  tone="rose"
                />
              </div>
            )}

            {error && (
              <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                {error}
              </div>
            )}

            {/* Candidates table */}
            <section className="rounded-lg border border-ink-700 bg-ink-900 overflow-hidden">
              <div className="px-3 py-2 border-b border-ink-700 text-xs font-semibold text-ink-300 flex items-center justify-between">
                <span>기회 후보 (총액 큰 순 · 점유율 낮은 순)</span>
                {loading && <span className="text-violet-300 text-[10px]">로딩 중…</span>}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-ink-800 text-ink-400">
                    <tr>
                      <th className="text-left px-3 py-2">회원</th>
                      <th className="text-left px-2 py-2">등급</th>
                      <th className="text-left px-2 py-2">카테고리</th>
                      <th className="text-right px-2 py-2">우리 매출</th>
                      <th className="text-right px-2 py-2">외부 지출</th>
                      <th className="text-right px-2 py-2">총액</th>
                      <th className="text-right px-2 py-2">점유율</th>
                      <th className="text-right px-3 py-2">미점유</th>
                      <th className="text-right px-3 py-2">churn</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.candidates.map((c, i) => (
                      <tr
                        key={`${c.member_id}-${c.industry_id}`}
                        className={`border-t border-ink-700/60 ${i % 2 === 0 ? 'bg-ink-900' : 'bg-ink-800/40'} hover:bg-ink-700/40`}
                      >
                        <td className="px-3 py-1.5">
                          <div className="text-ink-100">{c.name_ko}</div>
                          <div className="text-[10px] text-ink-500 font-mono">{c.member_id}</div>
                        </td>
                        <td className="px-2 py-1.5">
                          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${TIER_PALETTE[c.tier] ?? TIER_PALETTE.Bronze}`}>
                            {c.tier}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-ink-200">{c.industry_ko}</td>
                        <td className="px-2 py-1.5 text-right text-ink-300 font-mono">{fmtKrw(c.our_spend_krw)}</td>
                        <td className="px-2 py-1.5 text-right text-ink-300 font-mono">{fmtKrw(c.external_spend_krw)}</td>
                        <td className="px-2 py-1.5 text-right text-ink-100 font-mono">{fmtKrw(c.total_spend_krw)}</td>
                        <td className="px-2 py-1.5 text-right">
                          <span className={`font-mono ${c.our_share < 0.1 ? 'text-rose-300' : c.our_share < 0.2 ? 'text-amber-300' : 'text-ink-300'}`}>
                            {(c.our_share * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-right text-emerald-300 font-mono font-semibold">{fmtKrw(c.untapped_krw)}</td>
                        <td className={`px-3 py-1.5 text-right font-mono ${c.churn_risk >= 0.7 ? 'text-rose-300' : c.churn_risk >= 0.4 ? 'text-amber-300' : 'text-emerald-300'}`}>
                          {c.churn_risk.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                    {data && data.candidates.length === 0 && (
                      <tr>
                        <td colSpan={9} className="text-center py-8 text-ink-400">
                          현재 임계로 매칭되는 후보가 없습니다 — 임계를 완화해 보세요.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <footer className="text-[11px] text-ink-500 italic">
              ※ 합성 데이터(deterministic). 외부 소비는 NICE/마이데이터 스타일 패널 데이터를
              모방한 quarterly KRW 추정치입니다. 실 운영에서는 1:1 매칭 confidence를 엣지 속성으로
              두고 임계 필터링이 필요 (ADR-0005 참조).
            </footer>
          </>
        ) : (
          <div className="rounded-lg border border-ink-700 bg-ink-900 px-6 py-12 text-center">
            <Lock className="w-8 h-8 text-ink-500 mx-auto mb-2" />
            <div className="text-sm text-ink-300 font-semibold">{TAB_META[tab].ko} — 다음 반복</div>
            <div className="text-xs text-ink-500 mt-2 max-w-md mx-auto leading-relaxed">
              {TAB_META[tab].oneLiner}.
              현재 데이터 모델(IndustryCategory + HAS_CATEGORY_SPEND + 내부 Transaction) 위에서
              Cypher 한 개로 식별 가능합니다. 별도 PR로 추가 예정.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function KpiCard({
  icon: Icon, label, value, sub, tone = 'violet',
}: {
  icon: any;
  label: string;
  value: string;
  sub?: string;
  tone?: 'violet' | 'emerald' | 'amber' | 'rose';
}) {
  const TONE: Record<string, string> = {
    violet:  'text-violet-300 bg-violet-500/10 border-violet-500/30',
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
      <div className="text-base font-bold text-ink-50 leading-tight">{value}</div>
      {sub && <div className="text-[11px] text-ink-400 mt-0.5">{sub}</div>}
    </div>
  );
}
