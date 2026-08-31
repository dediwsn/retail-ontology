'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Truck, Snowflake, Building2, Package, Activity, AlertTriangle, Boxes,
  MessageSquare, ListChecks,
} from 'lucide-react';

import * as api from '@/lib/api-client';
import { useActivePersona } from '@/lib/persona-context';
import { KoreaMapView, Marker as MapMarker, Lane } from '@/components/map/KoreaMapView';
import { LogisticsChatPanel } from '@/components/LogisticsChatPanel';

type RightTab = 'detail' | 'chat';

const TYPE_LABEL: Record<string, string> = {
  mfr:      '제조사 DC',
  rdc:      '채널 RDC',
  '3pl':    '3PL 허브',
  lastmile: 'Last-mile',
};

export default function LogisticsPage() {
  const [data, setData] = useState<api.LogisticsNetworkResponse | null>(null);
  const [kpi, setKpi] = useState<api.LogisticsKpi | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedWh, setSelectedWh] = useState<string | null>(null);
  const [detail, setDetail] = useState<api.WarehouseDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [inventory, setInventory] = useState<api.InventoryListResponse | null>(null);
  const [showLanes, setShowLanes] = useState(true);
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set(['mfr','rdc','3pl','lastmile']));
  const [rightTab, setRightTab] = useState<RightTab>('detail');
  const { active } = useActivePersona();

  useEffect(() => {
    api.logisticsNetwork(active?.id).then(setData).catch((e) =>
      setError(e instanceof Error ? e.message : String(e))
    ).finally(() => setLoading(false));
    api.logisticsStatus().then(setKpi).catch(() => { /* KPI is non-essential */ });
    // Re-fetch on persona change: the topology is identical, but every region and
    // warehouse gains persona_member_count so the map can shade demand.
  }, [active?.id]);

  useEffect(() => {
    if (!selectedWh) { setDetail(null); setInventory(null); return; }
    let cancelled = false;
    // Switch back to detail tab when user clicks a warehouse on the map.
    setRightTab('detail');
    setDetailLoading(true);
    api.warehouseDetail(selectedWh)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    api.inventoryAtWarehouse(selectedWh, 30)
      .then((inv) => { if (!cancelled) setInventory(inv); })
      .catch(() => { if (!cancelled) setInventory(null); });
    return () => { cancelled = true; };
  }, [selectedWh]);

  // Build markers + lanes from network response.
  const markers: MapMarker[] = useMemo(() => {
    if (!data) return [];
    return data.warehouses
      .filter((w) => typeFilter.has(w.type))
      .map((w) => ({
        id: w.wh_id,
        name: w.name_ko,
        type: w.type,
        coordinates: [w.lng, w.lat] as [number, number],
        cold: w.cold_chain,
        tone: selectedWh === w.wh_id ? 'highlight' : 'normal',
      }));
  }, [data, selectedWh, typeFilter]);

  const lanes: Lane[] = useMemo(() => {
    if (!data || !showLanes) return [];
    const whById = new Map(data.warehouses.map((w) => [w.wh_id, w]));
    const visible = (id: string) => {
      const w = whById.get(id);
      return w ? typeFilter.has(w.type) : false;
    };
    return data.routes
      .filter((r) => visible(r.from_wh_id) && visible(r.to_wh_id))
      .map((r) => {
        const a = whById.get(r.from_wh_id);
        const b = whById.get(r.to_wh_id);
        if (!a || !b) return null;
        return {
          id: r.route_id,
          from: [a.lng, a.lat] as [number, number],
          to:   [b.lng, b.lat] as [number, number],
          carrier_id: r.carrier_id,
        };
      })
      .filter(Boolean) as Lane[];
  }, [data, showLanes, typeFilter]);

  const toggleType = (t: string) => {
    const n = new Set(typeFilter);
    if (n.has(t)) n.delete(t); else n.add(t);
    setTypeFilter(n);
  };

  const selectedWhRow = data && selectedWh
    ? data.warehouses.find((w) => w.wh_id === selectedWh) || null
    : null;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 border-b border-ink-700 bg-ink-900 flex items-center px-6">
        <div className="text-xs text-ink-400">시나리오 H · 물류 네트워크</div>
        <span className="ml-3 text-[10px] font-mono px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-300 border border-teal-500/30">
          한국 17 시도 · {data?.warehouses.length ?? '…'} 거점 · {data?.routes.length ?? '…'} lane
        </span>
      </header>

      <div className="flex-1 px-6 py-6 max-w-[1500px] mx-auto w-full flex flex-col gap-5 min-h-0">
        <div>
          <h1 className="text-2xl font-bold text-ink-50 mb-1 flex items-center gap-2">
            <Truck className="w-6 h-6 text-teal-400" /> 물류 네트워크
          </h1>
          <p className="text-sm text-ink-400">
            제조사 DC → 3PL 허브 → 채널 RDC → Last-mile 거점을 한국 지도에 시각화. 거점 클릭 시 입출고 route + 최근 shipment 30건 표시.
          </p>
        </div>

        {/* KPI strip — 5 cards */}
        {kpi && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5">
            <KpiCard
              icon={Activity}
              label="활성 출하"
              value={(kpi.in_transit + kpi.delayed).toLocaleString()}
              sub={`${kpi.in_transit.toLocaleString()} in-transit · ${kpi.delayed.toLocaleString()} 지연`}
              tone="cyan"
            />
            <KpiCard
              icon={Activity}
              label="OTD 준수율"
              value={`${(kpi.on_time_rate * 100).toFixed(1)}%`}
              sub={`${kpi.delivered.toLocaleString()} / ${kpi.total_shipments.toLocaleString()} 배송 완료`}
              tone={kpi.on_time_rate >= 0.7 ? 'emerald' : 'amber'}
            />
            <KpiCard
              icon={Truck}
              label="평균 transit"
              value={`${kpi.avg_transit_hours}h`}
              sub="route 계획 기준 가중 평균"
              tone="teal"
            />
            <KpiCard
              icon={AlertTriangle}
              label="예외 출하"
              value={kpi.exception.toLocaleString()}
              sub="paret damaged · 재처리 필요"
              tone={kpi.exception > 0 ? 'rose' : 'emerald'}
            />
            <KpiCard
              icon={AlertTriangle}
              label="활성 이벤트"
              value={kpi.active_events.toLocaleString()}
              sub="severity ≥ 3"
              tone={kpi.active_events > 0 ? 'amber' : 'emerald'}
            />
          </div>
        )}

        <div className="flex flex-wrap gap-2 items-center">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-ink-400">거점 유형:</span>
            {(['mfr','rdc','3pl','lastmile'] as const).map((t) => (
              <button
                key={t}
                onClick={() => toggleType(t)}
                className={[
                  'text-xs px-2.5 py-1 rounded-full border transition',
                  typeFilter.has(t)
                    ? 'border-teal-500/60 bg-teal-500/15 text-teal-200'
                    : 'border-ink-700 bg-ink-800 text-ink-400',
                ].join(' ')}
              >
                {TYPE_LABEL[t]}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowLanes((s) => !s)}
            className={[
              'text-xs px-3 py-1 rounded border transition ml-2',
              showLanes
                ? 'border-teal-500/60 bg-teal-500/15 text-teal-200'
                : 'border-ink-700 bg-ink-800 text-ink-400',
            ].join(' ')}
          >
            {showLanes ? 'Lane 표시' : 'Lane 숨김'}
          </button>
        </div>

        {error && (
          <div className="p-3 rounded-md bg-red-500/10 text-red-300 border border-red-500/30 text-sm">
            오류: {error}
          </div>
        )}
        {loading && !data && (
          <div className="text-sm text-ink-400 italic">네트워크 로딩 중…</div>
        )}

        {data && (
          <div className="grid xl:grid-cols-[minmax(0,1fr)_380px] gap-5 flex-1 min-h-0">
            <section className="rounded-lg border border-ink-700 bg-ink-900 p-2 min-h-[720px] overflow-hidden">
              <KoreaMapView
                markers={markers}
                lanes={lanes}
                selectedMarkerId={selectedWh}
                onMarkerClick={(id) => setSelectedWh(id)}
                showLanes={showLanes}
                height={760}
              />
            </section>

            <aside className="rounded-lg border border-ink-700 bg-ink-900 flex flex-col min-h-[720px] xl:min-h-0 overflow-hidden">
              {/* Tab bar */}
              <div className="flex border-b border-ink-700 shrink-0">
                <button
                  onClick={() => setRightTab('detail')}
                  className={[
                    'flex-1 px-3 py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition border-b-2',
                    rightTab === 'detail'
                      ? 'border-teal-400 text-teal-200 bg-teal-500/5'
                      : 'border-transparent text-ink-400 hover:text-ink-200 hover:bg-ink-800/50',
                  ].join(' ')}
                >
                  <ListChecks className="w-3.5 h-3.5" />
                  거점·운송사
                </button>
                <button
                  onClick={() => setRightTab('chat')}
                  className={[
                    'flex-1 px-3 py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition border-b-2 relative',
                    rightTab === 'chat'
                      ? 'border-teal-400 text-teal-200 bg-teal-500/5'
                      : 'border-transparent text-ink-400 hover:text-ink-200 hover:bg-ink-800/50',
                  ].join(' ')}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  물류 도우미
                  {rightTab !== 'chat' && (
                    <span className="absolute top-1.5 right-3 w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse-soft" />
                  )}
                </button>
              </div>

              {/* Tab content */}
              <div className="flex-1 overflow-hidden p-3 min-h-0">
              {rightTab === 'chat' ? (
                <LogisticsChatPanel />
              ) : (
              <div className="h-full overflow-y-auto space-y-4 pr-1">
              {/* Carrier legend */}
              <section>
                <h2 className="text-xs uppercase tracking-wider text-ink-400 font-semibold mb-2">운송사</h2>
                <ul className="space-y-1">
                  {data.carriers.map((c) => (
                    <li key={c.carrier_id} className="flex items-center gap-2 text-xs">
                      <span
                        className="w-3 h-3 rounded-sm border border-ink-700"
                        style={{ backgroundColor: CARRIER_HEX[c.carrier_id] || '#64748b' }}
                      />
                      <span className="text-ink-200">{c.name_ko}</span>
                      <span className="text-[10px] font-mono text-ink-500 ml-auto">{c.mode}</span>
                    </li>
                  ))}
                </ul>
              </section>

              {/* Selected warehouse detail */}
              {selectedWh && (
                <section className="border-t border-ink-700 pt-3">
                  <h2 className="text-xs uppercase tracking-wider text-ink-400 font-semibold mb-2 flex items-center gap-1.5">
                    <Building2 className="w-3.5 h-3.5 text-teal-400" /> 선택된 거점
                  </h2>
                  {detailLoading && <p className="text-xs text-ink-500 italic">상세 로딩 중…</p>}
                  {detail && (
                    <div className="space-y-2">
                      <div>
                        <div className="text-sm font-semibold text-ink-100">{detail.name_ko}</div>
                        <div className="text-[11px] font-mono text-ink-400">
                          {TYPE_LABEL[detail.type]} · {detail.region_name_ko || detail.region_code}
                        </div>
                        <div className="text-[10px] text-ink-400 mt-1">
                          용량 {detail.capacity_pallets.toLocaleString()} pallets
                          {detail.cold_chain && (
                            <span className="ml-2 inline-flex items-center gap-0.5 text-cyan-300">
                              <Snowflake className="w-3 h-3" /> 냉장
                            </span>
                          )}
                          {detail.operator_label && <span className="ml-2 text-orange-300">운영: {detail.operator_label}</span>}
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-[11px]">
                        <div className="p-2 rounded border border-ink-700 bg-ink-800">
                          <div className="text-ink-400">입고 lane</div>
                          <div className="text-ink-100 font-mono">{detail.inbound_routes.length}</div>
                        </div>
                        <div className="p-2 rounded border border-ink-700 bg-ink-800">
                          <div className="text-ink-400">출고 lane</div>
                          <div className="text-ink-100 font-mono">{detail.outbound_routes.length}</div>
                        </div>
                      </div>
                      {detail.recent_shipments.length > 0 && (
                        <div>
                          <h3 className="text-[10px] uppercase tracking-wider text-ink-400 font-semibold mt-3 mb-1.5 flex items-center gap-1">
                            <Package className="w-3 h-3" /> 최근 shipment
                          </h3>
                          <ul className="space-y-1">
                            {detail.recent_shipments.slice(0, 8).map((s) => (
                              <li key={s.shipment_id}
                                  className="px-2 py-1 rounded border border-ink-700 bg-ink-800 text-[10px] flex items-center gap-2">
                                <span className="font-mono text-ink-300">{s.shipment_id}</span>
                                <span className={[
                                  'font-mono px-1.5 rounded',
                                  s.status === 'delivered' ? 'text-emerald-300 bg-emerald-500/10' :
                                  s.status === 'in_transit' ? 'text-cyan-300 bg-cyan-500/10' :
                                  s.status === 'delayed' ? 'text-amber-300 bg-amber-500/10' :
                                  'text-rose-300 bg-rose-500/10',
                                ].join(' ')}>
                                  {s.status}
                                </span>
                                <span className="text-ink-500 ml-auto">{s.dispatched_at?.slice(5)}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {inventory && inventory.rows.length > 0 && (
                        <div>
                          <h3 className="text-[10px] uppercase tracking-wider text-ink-400 font-semibold mt-3 mb-1.5 flex items-center gap-1">
                            <Boxes className="w-3 h-3" /> 보유 재고
                            <span className="ml-auto font-mono text-[9px] text-ink-500">
                              {inventory.total_skus} SKU · {inventory.total_pallets} pallets
                            </span>
                          </h3>
                          <ul className="space-y-1">
                            {inventory.rows.slice(0, 12).map((r) => {
                              const usage = r.capacity_pallets > 0
                                ? Math.min(100, Math.round((r.on_hand_pallets / r.capacity_pallets) * 100))
                                : 0;
                              return (
                                <li key={r.inv_id}
                                    className="px-2 py-1 rounded border border-ink-700 bg-ink-800 text-[10px]">
                                  <div className="flex items-center gap-2">
                                    <span className="text-ink-100 truncate flex-1" title={r.sku_id}>
                                      {r.sku_name_ko || r.sku_id}
                                    </span>
                                    {r.temperature === 'cold' && (
                                      <Snowflake className="w-3 h-3 text-cyan-400 shrink-0" />
                                    )}
                                    <span className="font-mono text-ink-200 shrink-0">
                                      {r.on_hand_pallets}/{r.capacity_pallets}p
                                    </span>
                                  </div>
                                  <div className="mt-0.5 flex items-center gap-1.5">
                                    <div className="flex-1 h-1 rounded bg-ink-900 overflow-hidden">
                                      <div
                                        className={[
                                          'h-full rounded',
                                          usage > 80 ? 'bg-rose-400' :
                                          usage > 50 ? 'bg-amber-400' : 'bg-emerald-400',
                                        ].join(' ')}
                                        style={{ width: `${usage}%` }}
                                      />
                                    </div>
                                    <span className="font-mono text-[9px] text-ink-500 shrink-0">
                                      {r.days_of_cover}일
                                    </span>
                                  </div>
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </section>
              )}
              {!selectedWh && (
                <div className="border-t border-ink-700 pt-3 text-xs text-ink-500 italic">
                  지도에서 거점을 클릭하면 상세 정보가 표시됩니다.
                  <button
                    onClick={() => setRightTab('chat')}
                    className="block mt-2 text-teal-300 hover:text-teal-200 not-italic"
                  >
                    또는 물류 도우미 탭에서 자연어로 질문하세요 →
                  </button>
                </div>
              )}
              </div>
              )}
              </div>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}

function KpiCard({
  icon: Icon, label, value, sub, tone,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string; value: string; sub: string;
  tone: 'cyan' | 'teal' | 'emerald' | 'amber' | 'rose';
}) {
  const tones: Record<typeof tone, string> = {
    cyan:    'border-cyan-500/40 text-cyan-300',
    teal:    'border-teal-500/40 text-teal-300',
    emerald: 'border-emerald-500/40 text-emerald-300',
    amber:   'border-amber-500/40 text-amber-300',
    rose:    'border-rose-500/40 text-rose-300',
  };
  return (
    <div className={`rounded-lg border bg-ink-800 p-3 ${tones[tone]}`}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider opacity-90">
        <Icon className="w-3 h-3" /> {label}
      </div>
      <div className="text-xl font-bold text-ink-50 font-mono mt-0.5">{value}</div>
      <div className="text-[10px] text-ink-400 mt-0.5 truncate" title={sub}>{sub}</div>
    </div>
  );
}

const CARRIER_HEX: Record<string, string> = {
  car_cj:      '#fb7185',
  car_hanjin:  '#60a5fa',
  car_lotte:   '#fbbf24',
  car_post:    '#a78bfa',
  car_coupang: '#34d399',
  car_pantos:  '#94a3b8',
  car_cold:    '#22d3ee',
};
