'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { ArrowLeftRight, Sparkles, Tag, Layers, Search as SearchIcon } from 'lucide-react';

import * as api from '@/lib/api-client';
import { useActivePersona } from '@/lib/persona-context';

const CytoscapeView = dynamic(
  () => import('@/components/graph/CytoscapeView').then((m) => m.CytoscapeView),
  { ssr: false },
);

export default function SubstitutePage() {
  const [samples, setSamples] = useState<api.SubstituteSampleProduct[] | null>(null);
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<api.SubstituteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sameBrandOk, setSameBrandOk] = useState(false);
  const { active } = useActivePersona();

  useEffect(() => {
    api.substituteSamples(15).then((r) => setSamples(r.items)).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true); setError(null); setResult(null);
    api.substitute(selected, sameBrandOk, 8, active?.id)
      .then((r) => { if (!cancelled) setResult(r); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selected, sameBrandOk, active?.id]);

  const filteredSamples = (samples ?? []).filter((p) => {
    if (!filter.trim()) return true;
    const f = filter.trim().toLowerCase();
    return p.name.toLowerCase().includes(f) || p.sku_id.toLowerCase().includes(f);
  });

  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 border-b border-ink-700 bg-ink-900 flex items-center px-6">
        <div className="text-xs text-ink-400">시나리오 F · 대체재 추천</div>
        <span className="ml-3 text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
          IN_CATEGORY ∩ HAS_INGREDIENT ∩ TARGETS_CONCERN ± price
        </span>
      </header>

      <div className="flex-1 grid xl:grid-cols-[340px_1fr_360px] min-h-0">
        {/* Picker */}
        <aside className="border-r border-ink-700 bg-ink-900 flex flex-col min-h-0">
          <div className="p-4 border-b border-ink-700">
            <h2 className="text-sm font-semibold text-ink-100 flex items-center gap-2">
              <ArrowLeftRight className="w-4 h-4 text-cyan-400" /> 원본 제품
            </h2>
            <p className="text-[10px] text-ink-400 mt-1 leading-relaxed">
              풍부한 성분/관심사 fanout 기준 상위 15개. 클릭하면 같은 카테고리 대안을 점수 순으로 추천.
            </p>
          </div>
          <div className="px-3 py-2 border-b border-ink-700 relative">
            <SearchIcon className="absolute left-5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink-500" />
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="상품 필터"
              className="w-full rounded bg-ink-800 border border-ink-700 text-xs pl-8 pr-3 py-1.5 text-ink-100 outline-none focus:border-cyan-500 placeholder:text-ink-500" />
          </div>
          <div className="px-4 py-2 border-b border-ink-700 flex items-center gap-2 text-xs">
            <input type="checkbox" id="same-brand" checked={sameBrandOk}
              onChange={(e) => setSameBrandOk(e.target.checked)} className="accent-cyan-500" />
            <label htmlFor="same-brand" className="text-ink-300">같은 브랜드 허용</label>
          </div>
          <ul className="flex-1 overflow-y-auto">
            {!samples && <li className="text-xs text-ink-500 italic p-4">로딩 중…</li>}
            {filteredSamples.map((p) => {
              const active = p.sku_id === selected;
              return (
                <li key={p.sku_id}>
                  <button onClick={() => setSelected(p.sku_id)}
                    className={[
                      'w-full text-left px-4 py-2.5 border-b border-ink-700/40 transition',
                      active ? 'bg-cyan-500/10 border-l-2 border-l-cyan-500' : 'hover:bg-ink-800',
                    ].join(' ')}>
                    <div className={`text-sm font-medium truncate ${active ? 'text-cyan-200' : 'text-ink-100'}`}>{p.name}</div>
                    <div className="flex items-center gap-2 mt-0.5 text-[10px] text-ink-400 font-mono">
                      <span>{p.sku_id}</span>
                      <span>·</span>
                      <span>{p.domain ?? ''}</span>
                      {p.price_krw && <><span>·</span><span>₩{p.price_krw.toLocaleString()}</span></>}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        {/* Center: original + candidates */}
        <section className="flex flex-col min-h-0 overflow-y-auto">
          <div className="px-6 py-5">
            <h1 className="text-2xl font-bold text-ink-50 mb-1 flex items-center gap-2">
              <ArrowLeftRight className="w-6 h-6 text-cyan-400" /> 대체재 추천
            </h1>
            <p className="text-sm text-ink-400">
              같은 카테고리 + 성분/관심사 겹침 + 가격대 근접도 = 점수. 점수 옆 태그가 “왜 대체재인가”를 직접 보여줍니다.
            </p>
          </div>

          {error && <div className="mx-6 mb-4 p-3 rounded-md bg-red-500/10 text-red-300 border border-red-500/30 text-sm">{error}</div>}
          {loading && <div className="mx-6 text-sm text-ink-400">분석 중…</div>}

          {result && (
            <div className="px-6 pb-6 space-y-5">
              <article className="p-5 rounded-lg border border-cyan-500/30 bg-gradient-to-br from-cyan-500/10 to-cyan-500/0">
                <div className="text-[10px] uppercase tracking-wider text-cyan-300 font-semibold mb-1">Original</div>
                <h2 className="text-lg font-bold text-ink-50">{String(result.original.name_ko ?? '')}</h2>
                <div className="flex gap-2 text-[10px] font-mono text-ink-300 mt-1">
                  <span><Tag className="inline w-3 h-3 mr-1" />{String(result.original.brand_id ?? '')}</span>
                  <span><Layers className="inline w-3 h-3 mr-1" />{String(result.category.retail_category_ko ?? result.category.gs1_brick_name_en ?? '')}</span>
                  {Boolean(result.original.price_krw) && <span>₩{Number(result.original.price_krw).toLocaleString()}</span>}
                </div>
              </article>

              <article>
                <h3 className="text-sm font-semibold text-ink-100 mb-2 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-cyan-400" /> 대체재 후보 ({result.candidates.length})
                </h3>
                <ul className="space-y-2">
                  {result.candidates.map((c) => (
                    <li key={c.sku_id} className="p-3 rounded-md border border-ink-700 bg-ink-800">
                      <div className="flex items-start justify-between gap-3 mb-1">
                        <div className="text-sm text-ink-100 line-clamp-2 flex-1">{c.name}</div>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 shrink-0">
                          score {c.score}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        <Tag className="w-3 h-3 text-ink-400" />
                        <span className="text-[10px] font-mono text-ink-400">{c.brand_id ?? ''}</span>
                        <span className="text-[10px] font-mono text-ink-400">·</span>
                        {c.price_krw && (
                          <span className="text-[10px] font-mono text-ink-400">
                            ₩{c.price_krw.toLocaleString()}
                            {c.price_delta_pct !== null && c.price_delta_pct !== undefined && (
                              <span className={c.price_delta_pct! > 0 ? 'text-amber-300 ml-1' : 'text-emerald-300 ml-1'}>
                                {c.price_delta_pct! > 0 ? '+' : ''}{c.price_delta_pct}%
                              </span>
                            )}
                          </span>
                        )}
                        {c.shared_ingredients.length > 0 && (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                            성분 +{c.shared_ingredients.length}
                          </span>
                        )}
                        {c.shared_concerns.length > 0 && (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300 border border-violet-500/30">
                            관심사 +{c.shared_concerns.length}
                          </span>
                        )}
                      </div>
                      {c.shared_ingredients.length > 0 && (
                        <div className="text-[10px] text-ink-400 mt-1.5 truncate">
                          공통: <span className="font-mono">{c.shared_ingredients.slice(0, 5).join(', ')}</span>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </article>
            </div>
          )}
          {!result && !loading && !error && (
            <div className="flex-1 flex items-center justify-center text-sm text-ink-500 italic px-6 text-center">
              좌측에서 원본 제품을 선택하세요.
            </div>
          )}
        </section>

        <aside className="border-l border-ink-700 bg-ink-900 p-3 min-h-[400px] xl:min-h-0">
          {result ? <CytoscapeView subgraph={result.subgraph} /> : (
            <div className="h-full flex items-center justify-center text-xs text-ink-500 italic">그래프</div>
          )}
        </aside>
      </div>
    </div>
  );
}
