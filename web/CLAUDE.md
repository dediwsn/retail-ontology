# web/CLAUDE.md — Next.js 14 frontend

## Role

Scenario UIs (A–M), knowledge-graph object explorer, ontology meta views, operations console, plus a `/codegraph` meta page embedding the graphify-generated AST graph. App Router + standalone build for ECS Fargate ARM64. Auth is enforced upstream by Lambda@Edge — pages assume `id_token` cookie is already present and valid.

## Layout

- `app/(shopper)/` — route group for shopper-facing scenarios (search, chat, price).
- `app/(md)/` — route group for MD-facing scenarios (insights).
- `app/match/`, `app/safety/`, `app/substitute/`, `app/price/`, `app/churn/`, `app/acquisition/`, `app/tier-up/`, `app/coverage/`, `app/vip/` — top-level scenario routes for D, E, F, G, I, J, K, L, M respectively.
- `app/codegraph/` — meta page embedding `web/public/codegraph/graph.html` (graphify static bundle) with optional community side-panel powered by `community_meta.json`.
- `app/objects/[type]/` — dynamic Knowledge Graph object explorer (20 types: product, ingredient, concern, trend, brand, category, persona, channel, manufacturer, review, region, warehouse, carrier, event, member, tier, campaign, transaction, touchpoint, **industry_category**).
- `app/ops/[area]/` — dynamic operations console (ingest, guardrail, memory, eval, trace).
- `app/{schema,standards,validation}/` — ontology meta views.
- `app/logistics/page.tsx` — Scenario H: Korean choropleth map + KPI strip + tabbed right panel (거점·운송사 / 물류 도우미).
- `components/` — shared widgets: `Sidebar`, `SidebarAuth`, `PersonaSwitch`, `GuidedTour`, `CytoscapeView`, `LogisticsChatPanel`.
- `components/map/KoreaMapView.tsx` — react-simple-maps + d3-geo wrapper, consumes `public/korea-provinces.json` (KOSTAT 17-sido, 146 KB) with 5:4 viewBox.
- `lib/api-client.ts` — typed REST + SSE client. Single file; one function per endpoint.
- `lib/persona-context.tsx` — global active-persona React Context backed by localStorage.

## Conventions

- **Page outer shell**: every scenario page uses `min-h-screen flex flex-col` + `header.h-14` + `flex-1 px-6 py-6 max-w-[1500px] mx-auto w-full flex flex-col gap-5`. Order is title → form → chips → workspace.
- **Color identity per scenario**: A=blue, B=emerald, C=amber, D=violet, E=rose, F=cyan, G=sky, H=teal, I=orange, J=fuchsia, K=yellow, L=lime, **M=indigo**. Defined in `web/app/page.tsx:CARD_COLOR` and used by sidebar badges + scenario pages. Don't unify — they're navigation aids.
- **Sidebar header layout** — `flex justify-between` with truncating title block on the left + `<CompanyLogo />` button on the right. CompanyLogo cycles through 4 SVG presets (`web/public/logos/{aws,demo-blue,demo-emerald,demo-violet}.svg`) on click, persists in localStorage (`ontology-retail.company-logo`). Default preset overridable at build time via `NEXT_PUBLIC_DEFAULT_LOGO_PRESET=<id>` (defaults to `aws`). For demo prep: drop a real brand SVG into `web/public/logos/` + register in `LOGO_PRESETS`. See [web/public/logos/README.md](public/logos/README.md).
- **PersonaSwitch convention** — widget calls `api.listPersonas(50, { segment_eligible: true })` to fetch only spine + bridged narratives (~14 items) and renders them in two groups ("5-spine 페르소나" with SPINE badge, then "Narrative (bridged)"). Picking any visible persona is guaranteed to return non-zero members in I/J/K /map and L endpoints. Other narrative-rich scenarios (`/match`) keep the original 40-narrative list (no flag).
- **Card shading hierarchy**: page = `bg-ink-950`, panel = `bg-ink-900`, card = `bg-ink-800`, sub-card = `bg-ink-900` (one step darker than its parent card).
- **Markdown rendering**: chat and insights answers go through `react-markdown` v10 + `remark-gfm` under `.chat-markdown` styles in `globals.css`.
- **SSE consumption**: use `api.streamSSE<T>` or scenario-specific wrappers (`api.searchStream`, `api.insightsStream`, `api.chatStream`).
- **Persona injection**: pages that depend on the active persona call `useActivePersona()` and pass `persona: activePersona?.id` to API calls (search, chat, price).
- **Sample chip activation**: `onClick={() => { setQ(s); runSearch(s); }}` — pass the value to the runner directly rather than relying on state-set-then-call.

## Adding a new scenario

1. Create `app/<slug>/page.tsx` with `'use client'` directive.
2. Mirror the search/insights skeleton: header → title → form → chips → result panel.
3. Pick a unique color for the scenario (Tailwind palette).
4. Add the API client function in `lib/api-client.ts` with full TypeScript types.
5. Add a sidebar entry in `components/Sidebar.tsx` under `시나리오` with the next badge letter.
6. Add a step to `components/GuidedTour.tsx`'s `STEPS` array.

## TypeScript validation

```bash
cd web && npx tsc --noEmit
```

Always run before pushing — the Docker build does the same and a failure breaks deploy.
