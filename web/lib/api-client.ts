/**
 * API client for FastAPI endpoints (api/routers).
 * Base URL: same origin (CloudFront → ALB listener routes /api/* → tg-api).
 * In dev, set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 to hit local FastAPI.
 */
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

export type SearchHit = {
  sku_id: string;
  score: number;
  text: string;
  metadata: Record<string, unknown>;
};

export type GraphNode = { data: { id: string } & Record<string, unknown> };
export type GraphEdge = { data: { source: string; target: string; label?: string } & Record<string, unknown> };
export type Subgraph = { nodes: GraphNode[]; edges: GraphEdge[] };

export type SearchResponse = {
  hits: SearchHit[];
  subgraph: Subgraph;
  query_echo: string;
};

export async function search(
  q: string,
  opts: { topK?: number; persona?: string; includeSubgraph?: boolean } = {},
): Promise<SearchResponse> {
  const res = await fetch(`${BASE}/api/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      q,
      top_k: opts.topK ?? 10,
      persona: opts.persona,
      include_subgraph: opts.includeSubgraph ?? true,
    }),
  });
  if (!res.ok) throw new Error(`search failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// SSE streaming variant — emits phase events (bm25 / knn / rrf / rerank)
// before the final result event so the UI can show progress instead of
// a blank loading state.
export type SearchPhase = { name: string; detail?: string; ms?: number };
export type SearchEvent =
  | { type: 'phase'; data: SearchPhase }
  | { type: 'result'; data: SearchResponse };

export async function searchStream(
  body: { q: string; topK?: number; persona?: string; includeSubgraph?: boolean },
  onEvent: (event: SearchEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/api/search/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      q: body.q,
      top_k: body.topK ?? 10,
      persona: body.persona,
      include_subgraph: body.includeSubgraph ?? true,
    }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`search/stream failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      let type = '';
      let dataLine = '';
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) type = line.slice(7).trim();
        else if (line.startsWith('data: ')) dataLine = line.slice(6);
      }
      if (!type || !dataLine) continue;
      try {
        onEvent({ type, data: JSON.parse(dataLine) } as SearchEvent);
      } catch {
        /* ignore malformed frames */
      }
    }
  }
}

export type ChatPhase = { name: string; detail?: string };
export type ChatEvent =
  | { type: 'phase'; data: ChatPhase }
  | { type: 'log'; data: { tool: string; input: unknown } }
  | { type: 'delta'; data: { text: string } }
  | { type: 'guardrail'; data: { action: string } }
  | { type: 'stop'; data: { final: string } };

/**
 * SSE consumer for POST /api/chat.
 * EventSource only supports GET, so we use fetch + ReadableStream parser.
 */
export async function chatStream(
  body: { session_id: string; message: string; actor_id?: string },
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const evt = parseSseFrame(frame);
      if (evt) onEvent(evt);
    }
  }
}

function parseSseFrame(raw: string): ChatEvent | null {
  let type = '';
  let dataLine = '';
  for (const line of raw.split('\n')) {
    if (line.startsWith('event: ')) type = line.slice(7).trim();
    else if (line.startsWith('data: ')) dataLine = line.slice(6);
  }
  if (!type || !dataLine) return null;
  try {
    return { type, data: JSON.parse(dataLine) } as ChatEvent;
  } catch {
    return null;
  }
}

export type InsightsResponse = {
  answer_ko: string;
  chart_spec: { type: string; title: string; data: { label: string; value: number }[] };
  drill_down_subgraph: Subgraph;
};

export async function insights(q: string, periodDays = 28): Promise<InsightsResponse> {
  const res = await fetch(`${BASE}/api/insights`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q, period_days: periodDays }),
  });
  if (!res.ok) throw new Error(`insights failed: ${res.status}`);
  return res.json();
}

export type InsightsPhase = { name: string; detail?: string };
export type InsightsEvent =
  | { type: 'phase'; data: InsightsPhase }
  | { type: 'delta'; data: { text: string } }
  | { type: 'result'; data: InsightsResponse };

export async function insightsStream(
  body: { q: string; periodDays?: number },
  onEvent: (event: InsightsEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/api/insights/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ q: body.q, period_days: body.periodDays ?? 28 }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`insights/stream failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      let type = '';
      let dataLine = '';
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) type = line.slice(7).trim();
        else if (line.startsWith('data: ')) dataLine = line.slice(6);
      }
      if (!type || !dataLine) continue;
      try {
        onEvent({ type, data: JSON.parse(dataLine) } as InsightsEvent);
      } catch {
        /* ignore */
      }
    }
  }
}

// ─── Scenario I — Churn Risk Diagnosis ─────────────────────────────────────

export type AtRiskMember = {
  member_id: string;
  name_ko: string;
  tier: string;
  persona_id: string | null;
  persona_label_ko: string | null;
  churn_risk: number;
  recency_days: number;
  frequency: number;
  ltv_krw: number;
  last_purchase_at: string | null;
};

export type PersonaRiskBucket = {
  persona_id: string;
  persona_label_ko: string;
  total: number;
  at_risk: number;
  avg_churn_risk: number;
};

export type TierRiskBucket = {
  tier: string;
  total: number;
  at_risk: number;
  avg_churn_risk: number;
  avg_ltv_krw: number;
};

export type RecommendedCampaign = {
  campaign_id: string;
  name_ko: string;
  type: string;
  channel: string;
  target_persona_ids: string[];
  expected_response_rate: number;
};

export type ChurnDashboardResponse = {
  summary: {
    total_members: number;
    high_risk_count: number;
    high_risk_pct: number;
    vip_at_risk_count: number;
    avg_recency_days: number;
  };
  top_at_risk: AtRiskMember[];
  persona_breakdown: PersonaRiskBucket[];
  tier_breakdown: TierRiskBucket[];
  recommended_winback: RecommendedCampaign[];
  subgraph: Subgraph;
};

export type ChurnMemberDetailResponse = {
  member: AtRiskMember;
  transactions: {
    transaction_id: string;
    ts: string;
    amount_krw: number;
    sku_id: string | null;
    product_name_ko: string | null;
  }[];
  touchpoints: {
    touchpoint_id: string;
    type: string;
    ts: string;
    responded: boolean;
    campaign_id: string | null;
    campaign_name_ko: string | null;
  }[];
  response_rate: number;
  recommended_campaign: RecommendedCampaign | null;
  subgraph: Subgraph;
};

export async function churnDashboard(topK = 30): Promise<ChurnDashboardResponse> {
  const res = await fetch(`${BASE}/api/churn/dashboard?top_k=${topK}`);
  if (!res.ok) throw new Error(`churn dashboard failed: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function churnMember(memberId: string): Promise<ChurnMemberDetailResponse> {
  const res = await fetch(`${BASE}/api/churn/member/${encodeURIComponent(memberId)}`);
  if (!res.ok) throw new Error(`churn member failed: ${res.status} ${await res.text()}`);
  return res.json();
}

export type ChurnRegionRow = {
  region_code: string;
  name_ko: string;
  members: number;
  at_risk: number;
  avg_churn_risk: number;
  avg_ltv_krw: number;
};

export type ChurnMapResponse = {
  persona_id: string | null;
  persona_label_ko: string | null;
  high_risk_threshold: number;
  regions: ChurnRegionRow[];
};

export async function churnMap(persona?: string | null): Promise<ChurnMapResponse> {
  const qs = persona ? `?persona=${encodeURIComponent(persona)}` : '';
  const res = await fetch(`${BASE}/api/churn/map${qs}`);
  if (!res.ok) throw new Error(`churn map failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// ─── Scenario J — Acquisition Channel ROI ──────────────────────────────────

export type CampaignRoi = {
  campaign_id: string;
  name_ko: string;
  channel: string;
  target_persona_ids: string[];
  cost_krw: number;
  sent: number;
  responded: number;
  response_rate: number;
  attributed_members: number;
  attributed_ltv_krw: number;
  roi: number;
};

export type ChannelRoi = {
  channel: string;
  sent: number;
  responded: number;
  response_rate: number;
  attributed_members: number;
  attributed_ltv_krw: number;
  cost_krw: number;
  roi: number;
};

export type PersonaChannelCell = {
  persona_id: string;
  persona_label_ko: string;
  channel: string;
  sent: number;
  responded: number;
  response_rate: number;
};

export type AcquisitionDashboardResponse = {
  summary: {
    total_campaigns: number;
    total_cost_krw: number;
    total_attributed_members: number;
    total_attributed_ltv_krw: number;
    blended_roi: number;
    best_channel: string | null;
    best_channel_roi: number;
  };
  campaigns: CampaignRoi[];
  channels: ChannelRoi[];
  persona_channel_matrix: PersonaChannelCell[];
};

export async function acquisitionDashboard(): Promise<AcquisitionDashboardResponse> {
  const res = await fetch(`${BASE}/api/acquisition/dashboard`);
  if (!res.ok) throw new Error(`acquisition dashboard failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// ─── Scenario K — Tier-up Path ─────────────────────────────────────────────

export type ProductLift = {
  sku_id: string;
  name_ko: string;
  domain: string | null;
  silver_buyers: number;
  gold_buyers: number;
  lift: number;
};

export type CategoryLift = {
  gs1_brick_code: string;
  name_ko: string;
  silver_buyers: number;
  gold_buyers: number;
  lift: number;
};

export type UpgradeCandidate = {
  member_id: string;
  name_ko: string;
  persona_id: string | null;
  persona_label_ko: string | null;
  ltv_krw: number;
  monetary_krw: number;
  frequency: number;
  recency_days: number;
  gap_to_gold_krw: number;
  churn_risk: number;
};

export type TierUpDashboardResponse = {
  summary: {
    silver_count: number;
    gold_count: number;
    silver_to_gold_ratio: number;
    candidates_count: number;
    avg_candidate_ltv_krw: number;
  };
  product_lift: ProductLift[];
  category_lift: CategoryLift[];
  upgrade_candidates: UpgradeCandidate[];
};

export async function tierUpDashboard(topK = 25): Promise<TierUpDashboardResponse> {
  const res = await fetch(`${BASE}/api/tier-up/dashboard?top_k=${topK}`);
  if (!res.ok) throw new Error(`tier-up dashboard failed: ${res.status} ${await res.text()}`);
  return res.json();
}

export type TierUpRegionRow = {
  region_code: string;
  name_ko: string;
  silver_count: number;
  gold_count: number;
  candidate_count: number;
  avg_silver_ltv_krw: number;
  avg_gap_to_gold_krw: number;
};

export type TierUpMapResponse = {
  persona_id: string | null;
  persona_label_ko: string | null;
  candidate_ltv_floor_krw: number;
  gold_threshold_krw: number;
  regions: TierUpRegionRow[];
};

export async function tierUpMap(persona?: string | null): Promise<TierUpMapResponse> {
  const qs = persona ? `?persona=${encodeURIComponent(persona)}` : '';
  const res = await fetch(`${BASE}/api/tier-up/map${qs}`);
  if (!res.ok) throw new Error(`tier-up map failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// ─── Scenario L — Coverage Map (회원-거점 커버리지) ────────────────────────

export type CoverageDimension = 'count' | 'churn' | 'ltv' | 'uncov';

export type WarehouseMarker = {
  warehouse_id: string;
  name_ko: string;
  type: string;          // mfr | rdc | 3pl | lastmile
  region_code: string;
  lat: number;
  lng: number;
};

export type RegionCoverage = {
  region_code: string;
  name_ko: string;
  lat: number;
  lng: number;
  members: number;
  avg_churn_risk: number;
  avg_ltv_krw: number;
  tier_mix: Record<string, number>;
  nearest_warehouse_id: string | null;
  nearest_warehouse_km: number | null;
  covered: boolean;
};

export type CoverageSummary = {
  persona_id: string | null;
  persona_label_ko: string | null;
  radius_km: number;
  total_members: number;
  covered_members: number;
  uncovered_members: number;
  coverage_pct: number;
  top_uncovered_region_code: string | null;
  top_uncovered_region_ko: string | null;
  top_uncovered_member_count: number;
};

export type CoverageDashboardResponse = {
  summary: CoverageSummary;
  regions: RegionCoverage[];
  warehouses: WarehouseMarker[];
};

export async function coverageDashboard(opts: {
  persona?: string | null;
  dimension?: CoverageDimension;
  radius_km?: number;
} = {}): Promise<CoverageDashboardResponse> {
  const qs = new URLSearchParams();
  if (opts.persona) qs.set('persona', opts.persona);
  qs.set('dimension', opts.dimension ?? 'count');
  qs.set('radius_km', String(opts.radius_km ?? 80));
  const res = await fetch(`${BASE}/api/coverage/dashboard?${qs}`);
  if (!res.ok) throw new Error(`coverage dashboard failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// ─── Scenario M — VIP Target Builder (외부 소비 + wallet share) ──────────

export type OpportunityCandidate = {
  member_id: string;
  name_ko: string;
  tier: string;
  persona_id: string | null;
  industry_id: string;
  industry_ko: string;
  our_spend_krw: number;
  external_spend_krw: number;
  total_spend_krw: number;
  our_share: number;          // 0..1
  untapped_krw: number;
  churn_risk: number;
};

export type OpportunitySummary = {
  persona_id: string | null;
  persona_label_ko: string | null;
  share_ceiling: number;
  total_floor_krw: number;
  candidate_count: number;
  distinct_member_count: number;
  sum_untapped_krw: number;
  avg_our_share: number;
  top_industry_id: string | null;
  top_industry_ko: string | null;
};

export type OpportunityResponse = {
  summary: OpportunitySummary;
  candidates: OpportunityCandidate[];
};

export async function vipOpportunity(opts: {
  persona?: string | null;
  share_ceiling?: number;
  total_floor_krw?: number;
  top_k?: number;
} = {}): Promise<OpportunityResponse> {
  const qs = new URLSearchParams();
  if (opts.persona) qs.set('persona', opts.persona);
  qs.set('share_ceiling', String(opts.share_ceiling ?? 0.3));
  qs.set('total_floor_krw', String(opts.total_floor_krw ?? 500_000));
  qs.set('top_k', String(opts.top_k ?? 30));
  const res = await fetch(`${BASE}/api/vip/opportunity?${qs}`);
  if (!res.ok) throw new Error(`vip opportunity failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// Whale — internal tier=VIP definition

export type WhaleCandidate = {
  member_id: string;
  name_ko: string;
  tier: string;
  persona_id: string | null;
  ltv_krw: number;
  monetary_krw: number;
  frequency: number;
  recency_days: number;
  churn_risk: number;
};

export type WhaleResponse = {
  summary: {
    persona_id: string | null;
    persona_label_ko: string | null;
    ltv_floor_krw: number;
    candidate_count: number;
    sum_ltv_krw: number;
    avg_recency_days: number;
    high_risk_count: number;
  };
  candidates: WhaleCandidate[];
};

export async function vipWhale(opts: {
  persona?: string | null;
  ltv_floor_krw?: number;
  top_k?: number;
} = {}): Promise<WhaleResponse> {
  const qs = new URLSearchParams();
  if (opts.persona) qs.set('persona', opts.persona);
  qs.set('ltv_floor_krw', String(opts.ltv_floor_krw ?? 5_000_000));
  qs.set('top_k', String(opts.top_k ?? 50));
  const res = await fetch(`${BASE}/api/vip/whale?${qs}`);
  if (!res.ok) throw new Error(`vip whale failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// Loyal — high our_share + meaningful total

export type LoyalCandidate = {
  member_id: string;
  name_ko: string;
  tier: string;
  persona_id: string | null;
  industry_id: string;
  industry_ko: string;
  our_spend_krw: number;
  external_spend_krw: number;
  total_spend_krw: number;
  our_share: number;
  churn_risk: number;
};

export type LoyalResponse = {
  summary: {
    persona_id: string | null;
    persona_label_ko: string | null;
    share_floor: number;
    total_floor_krw: number;
    candidate_count: number;
    distinct_member_count: number;
    sum_protected_krw: number;
    avg_our_share: number;
  };
  candidates: LoyalCandidate[];
};

export async function vipLoyal(opts: {
  persona?: string | null;
  share_floor?: number;
  total_floor_krw?: number;
  top_k?: number;
} = {}): Promise<LoyalResponse> {
  const qs = new URLSearchParams();
  if (opts.persona) qs.set('persona', opts.persona);
  qs.set('share_floor', String(opts.share_floor ?? 0.5));
  qs.set('total_floor_krw', String(opts.total_floor_krw ?? 300_000));
  qs.set('top_k', String(opts.top_k ?? 50));
  const res = await fetch(`${BASE}/api/vip/loyal?${qs}`);
  if (!res.ok) throw new Error(`vip loyal failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// Cross-category — single internal cat + big external different

export type CrossCategoryCandidate = {
  member_id: string;
  name_ko: string;
  tier: string;
  persona_id: string | null;
  internal_industry_ko: string | null;
  target_industry_id: string;
  target_industry_ko: string;
  external_spend_krw: number;
  churn_risk: number;
};

export type CrossCategoryResponse = {
  summary: {
    persona_id: string | null;
    persona_label_ko: string | null;
    external_floor_krw: number;
    candidate_count: number;
    distinct_member_count: number;
    sum_addressable_krw: number;
    top_target_industry_ko: string | null;
  };
  candidates: CrossCategoryCandidate[];
};

export async function vipCrossCategory(opts: {
  persona?: string | null;
  external_floor_krw?: number;
  top_k?: number;
} = {}): Promise<CrossCategoryResponse> {
  const qs = new URLSearchParams();
  if (opts.persona) qs.set('persona', opts.persona);
  qs.set('external_floor_krw', String(opts.external_floor_krw ?? 500_000));
  qs.set('top_k', String(opts.top_k ?? 50));
  const res = await fetch(`${BASE}/api/vip/cross-category?${qs}`);
  if (!res.ok) throw new Error(`vip cross-category failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// Trajectory — q1/q0 growth >= floor + tier != VIP

export type TrajectoryCandidate = {
  member_id: string;
  name_ko: string;
  tier: string;
  persona_id: string | null;
  industry_id: string;
  industry_ko: string;
  q0_amount_krw: number;
  q1_amount_krw: number;
  growth_ratio: number;
  churn_risk: number;
};

export type TrajectoryResponse = {
  summary: {
    persona_id: string | null;
    persona_label_ko: string | null;
    growth_floor: number;
    candidate_count: number;
    distinct_member_count: number;
    avg_growth_ratio: number;
    top_industry_ko: string | null;
  };
  candidates: TrajectoryCandidate[];
};

export async function vipTrajectory(opts: {
  persona?: string | null;
  growth_floor?: number;
  exclude_tier_vip?: boolean;
  top_k?: number;
} = {}): Promise<TrajectoryResponse> {
  const qs = new URLSearchParams();
  if (opts.persona) qs.set('persona', opts.persona);
  qs.set('growth_floor', String(opts.growth_floor ?? 1.2));
  qs.set('exclude_tier_vip', String(opts.exclude_tier_vip ?? true));
  qs.set('top_k', String(opts.top_k ?? 50));
  const res = await fetch(`${BASE}/api/vip/trajectory?${qs}`);
  if (!res.ok) throw new Error(`vip trajectory failed: ${res.status} ${await res.text()}`);
  return res.json();
}

// ─── Wide-scope passthroughs for scenarios D/E/F/G/H + objects + ontology + ops
//
// These functions exist to satisfy import-resolution from the untracked
// scenario pages (web/app/{logistics,match,ops,price,safety,schema,standards,
// substitute,validation}/...). The Python routers behind them are now all
// registered in api/main.py (commits 614be82 + 0499324) and return Pydantic-
// validated payloads. TS shapes are kept `any` here intentionally — adding
// them would require mirroring ~15 router Pydantic models that may still
// evolve. The pages access fields via dot-notation; TypeScript's structural
// typing lets `any` flow through.

export type ObjectListResponse = any;
export type ObjectDetailResponse = any;
export type SafetyProfile = any;
export type SafetyCheckResponse = any;
export type PersonaListItem = any;
export type PersonaMatchResponse = any;
export type SubstituteSampleProduct = any;
export type SubstituteResponse = any;
export type PriceCompareResponse = any;
export type SchemaResponse = any;
export type StandardsTableResponse = any;
export type ValidationCheck = any;
export type ValidationResponse = any;
export type LogisticsNetworkResponse = any;
export type LogisticsKpi = any;
export type WarehouseDetailResponse = any;
export type InventoryListResponse = any;
export type IngestStatus = any;
export type GuardrailResponse = any;
export type MemorySnapshot = any;
export type EvalResponse = any;
export type TraceResponse = any;
export type CostResponse = any;

async function _get<T = any>(path: string, label: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${label} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

async function _post<T = any>(path: string, body: unknown, label: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${label} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

// Object Explorer
export const listObjects = (type: string, limit = 30) =>
  _get<ObjectListResponse>(`/api/objects/${encodeURIComponent(type)}?limit=${limit}`, 'listObjects');
export const getObjectDetail = (type: string, id: string) =>
  _get<ObjectDetailResponse>(`/api/objects/${encodeURIComponent(type)}/${encodeURIComponent(id)}`, 'getObjectDetail');

// Safety (E)
export const listSafetyProfiles = () =>
  _get<SafetyProfile[]>(`/api/safety/profiles`, 'listSafetyProfiles');
export const safetyCheck = (body: unknown) =>
  _post<SafetyCheckResponse>(`/api/safety-check`, body, 'safetyCheck');

// Persona match (D)
export const listPersonas = (limit = 60, opts: { segment_eligible?: boolean } = {}) =>
  _get<PersonaListItem[]>(
    `/api/personas?limit=${limit}` +
      (opts.segment_eligible ? '&segment_eligible=true' : ''),
    'listPersonas',
  );
export const personaMatch = (personaId: string, topK = 10) =>
  _post<PersonaMatchResponse>(`/api/persona-match`, { persona_id: personaId, top_k: topK }, 'personaMatch');

// Substitute (F)
export const substituteSamples = (limit = 15) =>
  _get<SubstituteSampleProduct[]>(`/api/substitute/sample-products?limit=${limit}`, 'substituteSamples');
export const substitute = (
  skuId: string, sameBrandOk = false, topK = 8, persona?: string | null,
) =>
  _post<SubstituteResponse>(
    `/api/substitute`,
    { sku_id: skuId, same_brand_ok: sameBrandOk, top_k: topK, persona: persona ?? undefined },
    'substitute',
  );

// Price (G)
export const priceCompare = (q: string, opts: { topK?: number; persona?: string } = {}) =>
  _post<PriceCompareResponse>(`/api/price/compare`, {
    q,
    top_k: opts.topK ?? 3,
    persona: opts.persona,
  }, 'priceCompare');

// Ontology (meta)
export const ontologySchema = () =>
  _get<SchemaResponse>(`/api/ontology/schema`, 'ontologySchema');
export const ontologyStandards = () =>
  _get<{ items: any[] }>(`/api/ontology/standards`, 'ontologyStandards');
export const ontologyStandardsTable = (filename: string, limit = 500) =>
  _get<StandardsTableResponse>(`/api/ontology/standards/${encodeURIComponent(filename)}?limit=${limit}`, 'ontologyStandardsTable');
export const ontologyValidation = () =>
  _get<ValidationResponse>(`/api/ontology/validation`, 'ontologyValidation');

// Logistics (H)
export const logisticsNetwork = (persona?: string | null) =>
  _get<LogisticsNetworkResponse>(
    `/api/logistics/network${persona ? `?persona=${encodeURIComponent(persona)}` : ''}`,
    'logisticsNetwork',
  );
export const logisticsStatus = () =>
  _get<LogisticsKpi>(`/api/logistics/status`, 'logisticsStatus');
export const warehouseDetail = (whId: string) =>
  _get<WarehouseDetailResponse>(`/api/logistics/warehouse/${encodeURIComponent(whId)}`, 'warehouseDetail');
export const inventoryAtWarehouse = (whId: string, limit = 30) =>
  _get<InventoryListResponse>(`/api/logistics/inventory/wh/${encodeURIComponent(whId)}?limit=${limit}`, 'inventoryAtWarehouse');

// Ops console
export const opsIngest = () => _get<IngestStatus>(`/api/ops/ingest`, 'opsIngest');
export const opsGuardrail = (minutes = 60, limit = 40) =>
  _get<GuardrailResponse>(`/api/ops/guardrail?minutes=${minutes}&limit=${limit}`, 'opsGuardrail');
export const opsMemory = (sessionId?: string, topK = 30) => {
  const qp = sessionId ? `?session_id=${encodeURIComponent(sessionId)}&top_k=${topK}` : `?top_k=${topK}`;
  return _get<MemorySnapshot>(`/api/ops/memory${qp}`, 'opsMemory');
};
export const opsEval = (run = false) =>
  _get<EvalResponse>(`/api/ops/eval?run=${run}`, 'opsEval');
export const opsCost = (days = 7) =>
  _get<CostResponse>(`/api/ops/cost?days=${days}`, 'opsCost');
export const opsTrace = (limit = 50, sessionId?: string) => {
  const qp = sessionId ? `?limit=${limit}&session_id=${encodeURIComponent(sessionId)}` : `?limit=${limit}`;
  return _get<TraceResponse>(`/api/ops/trace${qp}`, 'opsTrace');
};
