'use client';

// Scenario M — VIP Target Builder.
//
// 5 tabs, 5 strategic axes on the same data model:
//   • Opportunity — points where our wallet share is low → growth upside
//   • Loyal       — points where our wallet share is high → defend / margin
//   • Whale       — internal tier=VIP — biggest current value
//   • Cross-cat   — single-category buyer + big external in different industry
//   • Trajectory  — Q1/Q0 growth ≥ 1.2 + tier != VIP — future VIP
//
// All persona-aware via spine-or-narrative OR pattern (ADR-0006).

import { useEffect, useMemo, useState } from 'react';
import {
  Wallet, AlertTriangle, TrendingUp, Crown, Sparkles, Target,
  ArrowUpRight, Layers,
} from 'lucide-react';

import * as api from '@/lib/api-client';
import { useActivePersona } from '@/lib/persona-context';

type VipTab = 'opportunity' | 'loyal' | 'whale' | 'cross_category' | 'trajectory';

const TAB_META: Record<VipTab, { ko: string; icon: any; oneLiner: string }> = {
  opportunity:    { ko: '기회 VIP',     icon: Target,
                    oneLiner: '큰 카테고리 지출 + 우리 점유율 < 30% — 가장 큰 성장 가능성' },
  loyal:          { ko: '충성 VIP',     icon: Crown,
                    oneLiner: '우리 점유율 ≥ 70% + 카테고리 총액 ≥ 1M — 가격 보호·VIP 컨시어지' },
  whale:          { ko: '내부 Whale',   icon: Wallet,
                    oneLiner: 'tier=VIP 직접 분류 + LTV ≥ 5M — 기존 정의' },
  cross_category: { ko: '인접 카테고리', icon: Layers,
                    oneLiner: '우리에게 한 카테고리만 사고 인접 외부 카테고리 큰 지출 — Up-sell' },
  trajectory:     { ko: '잠재 VIP',     icon: TrendingUp,
                    oneLiner: '내부·외부 지출 추세 ↑ + tier ≠ VIP — 잠재 VIP, 캠페인 우선' },
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

  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 border-b border-ink-700 bg-ink-900 flex items-center px-6">
        <div className="text-xs text-ink-400">시나리오 M · VIP 타깃 빌더 (외부 소비 데이터)</div>
        <span className="ml-3 text-[10px] font-mono px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300 border border-violet-500/30">
          멤버쉽 × IndustryCategory · 5축 wallet share 분석
        </span>
      </header>

      <div className="flex-1 px-6 py-6 max-w-[1500px] mx-auto w-full flex flex-col gap-5 min-h-0">
        <div>
          <h1 className="text-2xl font-bold text-ink-50 mb-1 flex items-center gap-2">
            <Target className="w-6 h-6 text-violet-400" /> VIP 타깃 빌더
          </h1>
          <p className="text-sm text-ink-400">
            외부 소비 패널 데이터를 멤버쉽 위에 얹어 5가지 VIP 정의를 동시 운용 — 성장(Opportunity) / 방어(Loyal) /
            현재가치(Whale) / 인접 확장(Cross-category) / 미래 방향(Trajectory). 같은 회원이 여러 셀에 동시 속할 수 있고,
            그 *교차*가 캠페인 우선순위 결정의 근거.
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
                title={meta.oneLiner}
                className={[
                  'px-4 py-2 text-xs font-semibold flex items-center gap-1.5 transition border-b-2 -mb-px whitespace-nowrap',
                  isActive ? 'border-violet-400 text-violet-200 bg-violet-500/5'
                           : 'border-transparent text-ink-300 hover:text-ink-100 hover:bg-ink-800/50',
                ].join(' ')}
              >
                <Icon className="w-3.5 h-3.5" />
                {meta.ko}
              </button>
            );
          })}
        </div>

        {tab === 'opportunity' && <OpportunityTab personaId={active?.id ?? null} personaLabel={active?.label} />}
        {tab === 'loyal' && <LoyalTab personaId={active?.id ?? null} personaLabel={active?.label} />}
        {tab === 'whale' && <WhaleTab personaId={active?.id ?? null} personaLabel={active?.label} />}
        {tab === 'cross_category' && <CrossCategoryTab personaId={active?.id ?? null} personaLabel={active?.label} />}
        {tab === 'trajectory' && <TrajectoryTab personaId={active?.id ?? null} personaLabel={active?.label} />}

        <footer className="text-[11px] text-ink-500 italic">
          ※ 합성 데이터(deterministic). 외부 소비는 NICE/마이데이터 스타일 패널 추정치이며, Q1 2026 + Q0 2025 두 분기 스냅샷.
          1:1 매칭 confidence는 운영 시스템에서는 엣지 속성으로 두고 임계 필터링 필요 (ADR-0005 참조).
        </footer>
      </div>
    </div>
  );
}


// ═══ Sub-tabs ═════════════════════════════════════════════════════════════


type TabProps = { personaId: string | null; personaLabel?: string };

function OpportunityTab({ personaId, personaLabel }: TabProps) {
  const [shareCeiling, setShareCeiling] = useState<number>(0.3);
  const [totalFloor, setTotalFloor] = useState<number>(500_000);
  const [data, setData] = useState<api.OpportunityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true); setError(null);
    api.vipOpportunity({ persona: personaId, share_ceiling: shareCeiling, total_floor_krw: totalFloor, top_k: 50 })
      .then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, [personaId, shareCeiling, totalFloor]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-4">
        <SliderControl
          label="우리 점유율 ≤" min={0.05} max={0.7} step={0.05}
          value={shareCeiling} onChange={setShareCeiling}
          format={(v) => `${Math.round(v * 100)}%`} width="w-12"
        />
        <SliderControl
          label="카테고리 총액 ≥" min={100_000} max={3_000_000} step={100_000}
          value={totalFloor} onChange={setTotalFloor}
          format={fmtKrw} width="w-16"
        />
        <PersonaBadge label={personaLabel} />
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          <KpiCard icon={Target} tone="violet"
            label="기회 후보 (member × category)"
            value={data.summary.candidate_count.toLocaleString()}
            sub={`고유 회원 ${data.summary.distinct_member_count}명`} />
          <KpiCard icon={ArrowUpRight} tone="emerald"
            label="총 미점유 금액 (untapped)"
            value={fmtKrw(data.summary.sum_untapped_krw)}
            sub={`현재 우리 점유 평균 ${(data.summary.avg_our_share * 100).toFixed(1)}%`} />
          <KpiCard icon={Sparkles} tone="amber"
            label="최다 기회 카테고리"
            value={data.summary.top_industry_ko ?? '없음'}
            sub={data.summary.top_industry_id ?? ''} />
          <KpiCard icon={AlertTriangle} tone="rose"
            label="필터 임계"
            value={`점유율 ≤ ${Math.round(data.summary.share_ceiling * 100)}%`}
            sub={`카테고리 총액 ≥ ${fmtKrw(data.summary.total_floor_krw)}`} />
        </div>
      )}

      <ErrorOrLoading error={error} loading={loading} />

      <CandidatesTable
        title="기회 후보 (총액 큰 순 · 점유율 낮은 순)"
        loading={loading}
        rows={data?.candidates ?? []}
        emptyMessage="현재 임계로 매칭되는 후보가 없습니다 — 임계를 완화해 보세요."
        columns={[
          { key: 'name', header: '회원', render: (c: api.OpportunityCandidate) => <NameCell name={c.name_ko} id={c.member_id} /> },
          { key: 'tier', header: '등급', render: (c: api.OpportunityCandidate) => <TierBadge tier={c.tier} /> },
          { key: 'cat',  header: '카테고리', render: (c: api.OpportunityCandidate) => c.industry_ko },
          { key: 'our',  header: '우리 매출', align: 'right', render: (c: api.OpportunityCandidate) => fmtKrw(c.our_spend_krw) },
          { key: 'ext',  header: '외부 지출', align: 'right', render: (c: api.OpportunityCandidate) => fmtKrw(c.external_spend_krw) },
          { key: 'tot',  header: '총액',      align: 'right', render: (c: api.OpportunityCandidate) => fmtKrw(c.total_spend_krw) },
          { key: 'sh',   header: '점유율',   align: 'right', render: (c: api.OpportunityCandidate) =>
                <ShareCell share={c.our_share} mode="low_is_red" /> },
          { key: 'unt',  header: '미점유',   align: 'right', emphasized: true,
            render: (c: api.OpportunityCandidate) =>
                <span className="text-emerald-300 font-mono font-semibold">{fmtKrw(c.untapped_krw)}</span> },
          { key: 'ch',   header: 'churn',    align: 'right', render: (c: api.OpportunityCandidate) =>
                <ChurnCell risk={c.churn_risk} /> },
        ]}
      />
    </>
  );
}


function LoyalTab({ personaId, personaLabel }: TabProps) {
  const [shareFloor, setShareFloor] = useState<number>(0.5);
  const [totalFloor, setTotalFloor] = useState<number>(300_000);
  const [data, setData] = useState<api.LoyalResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true); setError(null);
    api.vipLoyal({ persona: personaId, share_floor: shareFloor, total_floor_krw: totalFloor, top_k: 50 })
      .then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, [personaId, shareFloor, totalFloor]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-4">
        <SliderControl
          label="우리 점유율 ≥" min={0.3} max={0.95} step={0.05}
          value={shareFloor} onChange={setShareFloor}
          format={(v) => `${Math.round(v * 100)}%`} width="w-12"
        />
        <SliderControl
          label="카테고리 총액 ≥" min={100_000} max={3_000_000} step={100_000}
          value={totalFloor} onChange={setTotalFloor}
          format={fmtKrw} width="w-16"
        />
        <PersonaBadge label={personaLabel} />
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          <KpiCard icon={Crown} tone="amber"
            label="충성 후보 (member × category)"
            value={data.summary.candidate_count.toLocaleString()}
            sub={`고유 회원 ${data.summary.distinct_member_count}명`} />
          <KpiCard icon={Wallet} tone="emerald"
            label="보호 매출 (우리 매출 합계)"
            value={fmtKrw(data.summary.sum_protected_krw)}
            sub={`평균 점유율 ${(data.summary.avg_our_share * 100).toFixed(1)}%`} />
          <KpiCard icon={Sparkles} tone="violet"
            label="가격 인상 안전 세그먼트"
            value="defensive"
            sub="마진 보호 우선" />
          <KpiCard icon={AlertTriangle} tone="rose"
            label="필터 임계"
            value={`점유율 ≥ ${Math.round(data.summary.share_floor * 100)}%`}
            sub={`총액 ≥ ${fmtKrw(data.summary.total_floor_krw)}`} />
        </div>
      )}

      <ErrorOrLoading error={error} loading={loading} />

      <CandidatesTable
        title="충성 후보 (우리 매출 큰 순)"
        loading={loading}
        rows={data?.candidates ?? []}
        emptyMessage="현재 임계로 매칭되는 후보가 없습니다."
        columns={[
          { key: 'name', header: '회원', render: (c: api.LoyalCandidate) => <NameCell name={c.name_ko} id={c.member_id} /> },
          { key: 'tier', header: '등급', render: (c: api.LoyalCandidate) => <TierBadge tier={c.tier} /> },
          { key: 'cat',  header: '카테고리', render: (c: api.LoyalCandidate) => c.industry_ko },
          { key: 'our',  header: '우리 매출', align: 'right', emphasized: true,
            render: (c: api.LoyalCandidate) =>
                <span className="text-emerald-300 font-mono font-semibold">{fmtKrw(c.our_spend_krw)}</span> },
          { key: 'ext',  header: '외부', align: 'right', render: (c: api.LoyalCandidate) => fmtKrw(c.external_spend_krw) },
          { key: 'tot',  header: '총액', align: 'right', render: (c: api.LoyalCandidate) => fmtKrw(c.total_spend_krw) },
          { key: 'sh',   header: '점유율', align: 'right', render: (c: api.LoyalCandidate) =>
                <ShareCell share={c.our_share} mode="high_is_green" /> },
          { key: 'ch',   header: 'churn', align: 'right', render: (c: api.LoyalCandidate) =>
                <ChurnCell risk={c.churn_risk} /> },
        ]}
      />
    </>
  );
}


function WhaleTab({ personaId, personaLabel }: TabProps) {
  const [ltvFloor, setLtvFloor] = useState<number>(5_000_000);
  const [data, setData] = useState<api.WhaleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true); setError(null);
    api.vipWhale({ persona: personaId, ltv_floor_krw: ltvFloor, top_k: 50 })
      .then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, [personaId, ltvFloor]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-4">
        <SliderControl
          label="LTV ≥" min={3_000_000} max={20_000_000} step={500_000}
          value={ltvFloor} onChange={setLtvFloor}
          format={fmtKrw} width="w-16"
        />
        <PersonaBadge label={personaLabel} />
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          <KpiCard icon={Wallet} tone="amber"
            label="Whale 회원"
            value={data.summary.candidate_count.toLocaleString()}
            sub={`tier=VIP & LTV ≥ ${fmtKrw(data.summary.ltv_floor_krw)}`} />
          <KpiCard icon={Sparkles} tone="emerald"
            label="총 LTV 합계"
            value={fmtKrw(data.summary.sum_ltv_krw)}
            sub={`평균 미접속 ${data.summary.avg_recency_days}일`} />
          <KpiCard icon={AlertTriangle} tone="rose"
            label="고위험 (churn ≥ 0.7)"
            value={data.summary.high_risk_count.toLocaleString()}
            sub="이탈 방지 캠페인 1순위" />
          <KpiCard icon={Crown} tone="violet"
            label="액션"
            value="retention"
            sub="VIP 컨시어지·이탈 방지" />
        </div>
      )}

      <ErrorOrLoading error={error} loading={loading} />

      <CandidatesTable
        title="Whale 회원 (LTV 큰 순)"
        loading={loading}
        rows={data?.candidates ?? []}
        emptyMessage="현재 임계로 매칭되는 회원이 없습니다."
        columns={[
          { key: 'name', header: '회원', render: (c: api.WhaleCandidate) => <NameCell name={c.name_ko} id={c.member_id} /> },
          { key: 'tier', header: '등급', render: (c: api.WhaleCandidate) => <TierBadge tier={c.tier} /> },
          { key: 'ltv',  header: 'LTV',  align: 'right', emphasized: true,
            render: (c: api.WhaleCandidate) =>
                <span className="text-amber-300 font-mono font-semibold">{fmtKrw(c.ltv_krw)}</span> },
          { key: 'mon',  header: '누적 매출', align: 'right', render: (c: api.WhaleCandidate) => fmtKrw(c.monetary_krw) },
          { key: 'freq', header: 'F', align: 'right', render: (c: api.WhaleCandidate) => `${c.frequency}회` },
          { key: 'rec',  header: '미접속', align: 'right', render: (c: api.WhaleCandidate) => `${c.recency_days}일` },
          { key: 'ch',   header: 'churn', align: 'right', render: (c: api.WhaleCandidate) =>
                <ChurnCell risk={c.churn_risk} /> },
        ]}
      />
    </>
  );
}


function CrossCategoryTab({ personaId, personaLabel }: TabProps) {
  const [extFloor, setExtFloor] = useState<number>(500_000);
  const [data, setData] = useState<api.CrossCategoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true); setError(null);
    api.vipCrossCategory({ persona: personaId, external_floor_krw: extFloor, top_k: 50 })
      .then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, [personaId, extFloor]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-4">
        <SliderControl
          label="외부 지출 ≥" min={200_000} max={3_000_000} step={100_000}
          value={extFloor} onChange={setExtFloor}
          format={fmtKrw} width="w-16"
        />
        <PersonaBadge label={personaLabel} />
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          <KpiCard icon={Layers} tone="violet"
            label="인접 확장 후보"
            value={data.summary.candidate_count.toLocaleString()}
            sub={`고유 회원 ${data.summary.distinct_member_count}명`} />
          <KpiCard icon={ArrowUpRight} tone="emerald"
            label="총 인접 외부 지출"
            value={fmtKrw(data.summary.sum_addressable_krw)}
            sub="우리에게 0원, 외부에 모두" />
          <KpiCard icon={Sparkles} tone="amber"
            label="최다 진출 후보 카테고리"
            value={data.summary.top_target_industry_ko ?? '없음'}
            sub="cross-sell 1순위" />
          <KpiCard icon={AlertTriangle} tone="rose"
            label="필터 임계"
            value={`외부 ≥ ${fmtKrw(data.summary.external_floor_krw)}`}
            sub="우리에게 1개 카테고리만" />
        </div>
      )}

      <ErrorOrLoading error={error} loading={loading} />

      <CandidatesTable
        title="인접 카테고리 진출 후보 (외부 지출 큰 순)"
        loading={loading}
        rows={data?.candidates ?? []}
        emptyMessage="현재 임계로 매칭되는 후보가 없습니다."
        columns={[
          { key: 'name', header: '회원', render: (c: api.CrossCategoryCandidate) => <NameCell name={c.name_ko} id={c.member_id} /> },
          { key: 'tier', header: '등급', render: (c: api.CrossCategoryCandidate) => <TierBadge tier={c.tier} /> },
          { key: 'have', header: '우리에게 거래 카테고리', render: (c: api.CrossCategoryCandidate) =>
                <span className="text-ink-300">{c.internal_industry_ko ?? '—'}</span> },
          { key: 'tgt',  header: '외부 진출 후보 카테고리', render: (c: api.CrossCategoryCandidate) =>
                <span className="text-violet-300">{c.target_industry_ko}</span> },
          { key: 'ext',  header: '외부 지출', align: 'right', emphasized: true,
            render: (c: api.CrossCategoryCandidate) =>
                <span className="text-emerald-300 font-mono font-semibold">{fmtKrw(c.external_spend_krw)}</span> },
          { key: 'ch',   header: 'churn', align: 'right', render: (c: api.CrossCategoryCandidate) =>
                <ChurnCell risk={c.churn_risk} /> },
        ]}
      />
    </>
  );
}


function TrajectoryTab({ personaId, personaLabel }: TabProps) {
  const [growthFloor, setGrowthFloor] = useState<number>(1.2);
  const [data, setData] = useState<api.TrajectoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true); setError(null);
    api.vipTrajectory({ persona: personaId, growth_floor: growthFloor, exclude_tier_vip: true, top_k: 50 })
      .then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, [personaId, growthFloor]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-4">
        <SliderControl
          label="성장률 ≥" min={1.05} max={2.5} step={0.05}
          value={growthFloor} onChange={setGrowthFloor}
          format={(v) => `${v.toFixed(2)}×`} width="w-12"
        />
        <PersonaBadge label={personaLabel} />
        <span className="text-[10px] text-ink-500">tier=VIP 제외 (잠재 VIP 만)</span>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          <KpiCard icon={TrendingUp} tone="emerald"
            label="잠재 VIP 후보"
            value={data.summary.candidate_count.toLocaleString()}
            sub={`고유 회원 ${data.summary.distinct_member_count}명`} />
          <KpiCard icon={ArrowUpRight} tone="violet"
            label="평균 성장률 (Q1 / Q0)"
            value={`${data.summary.avg_growth_ratio.toFixed(2)}×`}
            sub={`임계 ${data.summary.growth_floor.toFixed(2)}× 이상만 집계`} />
          <KpiCard icon={Sparkles} tone="amber"
            label="최다 성장 카테고리"
            value={data.summary.top_industry_ko ?? '없음'}
            sub="조기 격상 캠페인 우선 노출" />
          <KpiCard icon={Crown} tone="rose"
            label="액션"
            value="early upgrade"
            sub="등급 격상 + 광고 ROI 최고" />
        </div>
      )}

      <ErrorOrLoading error={error} loading={loading} />

      <CandidatesTable
        title="잠재 VIP 후보 (성장률 큰 순)"
        loading={loading}
        rows={data?.candidates ?? []}
        emptyMessage="현재 임계로 매칭되는 후보가 없습니다 — 성장률 임계를 낮춰 보세요."
        columns={[
          { key: 'name', header: '회원', render: (c: api.TrajectoryCandidate) => <NameCell name={c.name_ko} id={c.member_id} /> },
          { key: 'tier', header: '등급', render: (c: api.TrajectoryCandidate) => <TierBadge tier={c.tier} /> },
          { key: 'cat',  header: '카테고리', render: (c: api.TrajectoryCandidate) => c.industry_ko },
          { key: 'q0',   header: '2025-Q4', align: 'right', render: (c: api.TrajectoryCandidate) => fmtKrw(c.q0_amount_krw) },
          { key: 'q1',   header: '2026-Q1', align: 'right', render: (c: api.TrajectoryCandidate) => fmtKrw(c.q1_amount_krw) },
          { key: 'g',    header: '성장률', align: 'right', emphasized: true,
            render: (c: api.TrajectoryCandidate) => (
              <span className={`font-mono font-semibold ${c.growth_ratio >= 2 ? 'text-emerald-300' : c.growth_ratio >= 1.5 ? 'text-amber-300' : 'text-violet-300'}`}>
                {c.growth_ratio.toFixed(2)}×
              </span>
            ) },
          { key: 'ch',   header: 'churn', align: 'right', render: (c: api.TrajectoryCandidate) =>
                <ChurnCell risk={c.churn_risk} /> },
        ]}
      />
    </>
  );
}


// ═══ Shared widgets ═══════════════════════════════════════════════════════


function KpiCard({
  icon: Icon, label, value, sub, tone = 'violet',
}: {
  icon: any; label: string; value: string; sub?: string;
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

function SliderControl({
  label, min, max, step, value, onChange, format, width,
}: {
  label: string; min: number; max: number; step: number;
  value: number; onChange: (v: number) => void;
  format: (v: number) => string; width: string;
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-ink-300">
      <span className="font-semibold">{label}</span>
      <input type="range" min={min} max={max} step={step}
        value={value} onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-32 accent-violet-400" />
      <span className={`font-mono text-ink-100 text-right ${width}`}>{format(value)}</span>
    </label>
  );
}

function PersonaBadge({ label }: { label?: string }) {
  if (!label) return null;
  return (
    <span className="text-xs text-ink-400">
      페르소나: <span className="text-violet-300 font-semibold">{label}</span>
    </span>
  );
}

function ErrorOrLoading({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) {
    return (
      <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
        {error}
      </div>
    );
  }
  return null;
}

function NameCell({ name, id }: { name: string; id: string }) {
  return (
    <div>
      <div className="text-ink-100">{name}</div>
      <div className="text-[10px] text-ink-500 font-mono">{id}</div>
    </div>
  );
}

function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${TIER_PALETTE[tier] ?? TIER_PALETTE.Bronze}`}>
      {tier}
    </span>
  );
}

function ShareCell({ share, mode }: { share: number; mode: 'low_is_red' | 'high_is_green' }) {
  const tone =
    mode === 'low_is_red'
      ? (share < 0.1 ? 'text-rose-300' : share < 0.2 ? 'text-amber-300' : 'text-ink-300')
      : (share >= 0.85 ? 'text-emerald-300' : share >= 0.7 ? 'text-amber-300' : 'text-ink-300');
  return <span className={`font-mono ${tone}`}>{(share * 100).toFixed(1)}%</span>;
}

function ChurnCell({ risk }: { risk: number }) {
  const tone = risk >= 0.7 ? 'text-rose-300' : risk >= 0.4 ? 'text-amber-300' : 'text-emerald-300';
  return <span className={`font-mono ${tone}`}>{risk.toFixed(2)}</span>;
}

type ColumnSpec<T> = {
  key: string;
  header: string;
  align?: 'left' | 'right';
  emphasized?: boolean;
  render: (row: T) => React.ReactNode;
};

function CandidatesTable<T>({
  title, loading, rows, columns, emptyMessage,
}: {
  title: string;
  loading: boolean;
  rows: T[];
  columns: ColumnSpec<T>[];
  emptyMessage: string;
}) {
  return (
    <section className="rounded-lg border border-ink-700 bg-ink-900 overflow-hidden">
      <div className="px-3 py-2 border-b border-ink-700 text-xs font-semibold text-ink-300 flex items-center justify-between">
        <span>{title}</span>
        {loading && <span className="text-violet-300 text-[10px]">로딩 중…</span>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-ink-800 text-ink-400">
            <tr>
              {columns.map((col) => (
                <th key={col.key} className={`px-2 py-2 ${col.align === 'right' ? 'text-right' : 'text-left'}`}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className={`border-t border-ink-700/60 ${i % 2 === 0 ? 'bg-ink-900' : 'bg-ink-800/40'} hover:bg-ink-700/40`}>
                {columns.map((col) => (
                  <td key={col.key} className={`px-2 py-1.5 ${col.align === 'right' ? 'text-right' : 'text-left'}`}>
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={columns.length} className="text-center py-8 text-ink-400">
                  {emptyMessage}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
