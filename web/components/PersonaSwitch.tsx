'use client';

// Global persona-switch widget rendered in the top-right of the layout.
// Lists 40 personas (lazy-loaded once); clicking sets the active persona
// for all scenario pages via PersonaContext. Designed to stay collapsed
// (compact pill) until clicked so it doesn't dominate the header.

import { useEffect, useRef, useState } from 'react';
import { ChevronDown, X, UserCheck } from 'lucide-react';

import * as api from '@/lib/api-client';
import { useActivePersona } from '@/lib/persona-context';

type PersonaItem = {
  persona_id: string;
  label: string;
  is_spine?: boolean;
  is_bridged?: boolean;
};

export function PersonaSwitch() {
  const { active, setActive } = useActivePersona();
  const [open, setOpen] = useState(false);
  const [list, setList] = useState<PersonaItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const popRef = useRef<HTMLDivElement | null>(null);

  // Lazy-load on first open. Backend filters to spine + bridged narratives
  // (segment_eligible=true) — narratives without a DERIVED_FROM bridge are
  // hidden because they always return 0 members on Coverage / Churn /map /
  // Tier-up /map. Result: ~15 personas (5 spine + 10 bridged) instead of 40.
  useEffect(() => {
    if (!open || list) return;
    api.listPersonas(50, { segment_eligible: true })
      .then((res) => {
        const items = res.items.map((p: any) => ({
          persona_id: p.persona_id,
          label: p.label_ko || p.persona_id,
          is_spine: !!p.is_spine,
          is_bridged: !!p.is_bridged,
        }));
        // Sort spine first, then bridged narratives, then alphabetical-ish.
        items.sort((a: PersonaItem, b: PersonaItem) => {
          if (a.is_spine !== b.is_spine) return a.is_spine ? -1 : 1;
          return a.persona_id.localeCompare(b.persona_id);
        });
        setList(items);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'load failed'));
  }, [open, list]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (popRef.current && !popRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const filtered = list?.filter((p) =>
    !filter || p.label.includes(filter) || p.persona_id.includes(filter)
  ) ?? [];

  return (
    <div className="relative" ref={popRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={[
          'flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs font-medium transition',
          active
            ? 'border-orange-500/40 bg-orange-500/10 text-orange-200 hover:bg-orange-500/15'
            : 'border-ink-700 bg-ink-800 text-ink-300 hover:border-ink-600',
        ].join(' ')}
      >
        <UserCheck className="w-3.5 h-3.5" />
        {active ? (
          <>
            <span className="max-w-[180px] truncate">{active.label}</span>
            <span
              role="button"
              aria-label="페르소나 해제"
              className="ml-0.5 -mr-1 p-0.5 rounded hover:bg-orange-500/20"
              onClick={(e) => { e.stopPropagation(); setActive(null); }}
            >
              <X className="w-3 h-3" />
            </span>
          </>
        ) : (
          <span>페르소나 선택</span>
        )}
        <ChevronDown className={`w-3 h-3 transition ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-[320px] rounded-lg border border-ink-700 bg-ink-900 shadow-xl shadow-black/50 z-50 overflow-hidden">
          <div className="p-2 border-b border-ink-700">
            <input
              autoFocus
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="페르소나 검색 (예: 임산부)"
              className="w-full rounded border border-ink-700 bg-ink-800 text-ink-100 px-3 py-1.5 text-xs outline-none focus:border-orange-500 placeholder:text-ink-500"
            />
          </div>
          <div className="max-h-[360px] overflow-y-auto">
            {error && <div className="p-3 text-xs text-red-300">오류: {error}</div>}
            {!list && !error && (
              <div className="p-3 text-xs text-ink-500 italic">로딩 중…</div>
            )}
            {list && filtered.length === 0 && (
              <div className="p-3 text-xs text-ink-500 italic">일치하는 페르소나가 없습니다.</div>
            )}
            <ul>
              {/* Group label — spine vs bridged narratives */}
              {filtered.length > 0 && filtered.some((p) => p.is_spine) && (
                <li className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-ink-500 font-semibold">
                  5-spine 페르소나
                </li>
              )}
              {filtered.filter((p) => p.is_spine).map((p) => (
                <PersonaRow key={p.persona_id} p={p} active={active}
                            onSelect={() => { setActive({ id: p.persona_id, label: p.label }); setOpen(false); }} />
              ))}
              {filtered.some((p) => !p.is_spine) && (
                <li className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-wider text-ink-500 font-semibold border-t border-ink-700/60 mt-1">
                  Narrative (bridged)
                </li>
              )}
              {filtered.filter((p) => !p.is_spine).map((p) => (
                <PersonaRow key={p.persona_id} p={p} active={active}
                            onSelect={() => { setActive({ id: p.persona_id, label: p.label }); setOpen(false); }} />
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

function PersonaRow({
  p, active, onSelect,
}: {
  p: PersonaItem;
  active: { id: string; label: string } | null;
  onSelect: () => void;
}) {
  const isActive = active?.id === p.persona_id;
  return (
    <li>
      <button
        onClick={onSelect}
        className={[
          'w-full text-left px-3 py-2 text-xs flex items-center justify-between gap-2 transition',
          isActive
            ? 'bg-orange-500/15 text-orange-200'
            : 'text-ink-300 hover:bg-ink-800',
        ].join(' ')}
      >
        <span className="truncate flex items-center gap-1.5">
          {p.is_spine && (
            <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-orange-500/20 text-orange-300 border border-orange-500/40">
              SPINE
            </span>
          )}
          {p.label}
        </span>
        <span className="font-mono text-[10px] text-ink-500 shrink-0">{p.persona_id}</span>
      </button>
    </li>
  );
}
