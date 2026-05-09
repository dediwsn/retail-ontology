# ADR-0011: Sidebar Configurable Company Logo — LocalStorage Cycle + Env Default

- Status: Accepted
- Date: 2026-05-08
- Deciders: whchoi (solo SA)
- Tags: ux, demo-friendly, sidebar, branding

## Context

The demo is presented to customers who naturally ask "can it show *our* logo?" During a meeting, the demonstrator should be able to switch the displayed brand **without rebuilding/restarting** the web container — the demo flow can't tolerate a 3-minute deploy cycle mid-conversation.

At the same time, *which* brand the page shows by default needs to be configurable — different sales calls have different default brands, and that decision belongs in deployment config, not source code.

## Decision

**Two layers, both opt-in:**

### Layer 1 — Default preset via env (build-time)

`NEXT_PUBLIC_DEFAULT_LOGO_PRESET=<id>` set in the `web` task-definition env block. The web image bundles 4 SVG presets in `web/public/logos/`:

```
web/public/logos/
  ├── aws.svg          ← default (NEXT_PUBLIC_DEFAULT_LOGO_PRESET unset)
  ├── demo-blue.svg    ← placeholder (B2B mfg-style)
  ├── demo-emerald.svg ← placeholder (retail demo)
  └── demo-violet.svg  ← placeholder (CPG demo)
```

`web/components/CompanyLogo.tsx:LOGO_PRESETS` is a single source of truth — adding a new preset = (1) drop SVG in `web/public/logos/` + (2) append to `LOGO_PRESETS`.

### Layer 2 — Live cycle via localStorage (runtime)

Click the logo → `useState(currentPresetId)` advances to the next preset in `LOGO_PRESETS`, persists in `localStorage` (key `ontology-retail.company-logo`). On next page load, the persisted choice overrides the env default.

A real demo flow looks like:
1. Sales prep: deploy with `NEXT_PUBLIC_DEFAULT_LOGO_PRESET=customer-brand`
2. Mid-meeting: customer says "can we see your other client's setup?" → demonstrator clicks logo → cycle to that brand → no reload, no auth refresh, no redeploy.

## Alternatives Considered

### A. Env-var-only swap (no live cycle)

Cleanest config, but breaks the "no rebuild during demo" requirement. **Rejected**.

### B. URL query param (`?logo=samsung`)

Stateless, no localStorage. **Rejected** — every internal nav (sidebar click, scenario page change) drops the param unless every internal `<Link>` re-injects it; risk of confusing UX.

### C. Database-backed user preference

Store preset choice in user profile / Cognito. **Rejected** — overengineered for a demo concern; localStorage is per-browser-tab which is exactly the right scope.

### D. CSS variable theming (logo as part of theme)

Treat logo as one piece of a full theme (logo + colors + fonts). **Rejected** for now — scope creep; current demos only need logo swap, not full re-skin.

## Consequences

### Positive

- **Zero-rebuild demo swap** — the killer feature. Click and go.
- **Low blast radius** — 1 component (`CompanyLogo.tsx`), 1 dir (`web/public/logos/`), 1 env var. Doesn't touch any other state.
- **Default override is standard 12-factor** — env var, ship the same image, customise per environment.
- **Trademark-clean defaults** — bundled presets are typographic / generic so no licensing concern; real brand SVGs are added by the demo team per call.

### Negative

- **`NEXT_PUBLIC_DEFAULT_LOGO_PRESET` is build-time** — Next.js bakes it at `next build`. Changing the *server-shipped default* requires a new image. Mitigated by Layer 2 (localStorage) covering the per-meeting cases.
- **Per-browser, not per-user** — localStorage is browser-scoped; switching browsers loses the cycle state. Acceptable for demo context (one demonstrator's browser).
- **No Korean i18n on AWS preset** — the bundled `aws.svg` is just typographic "AWS"; real AWS brand assets aren't redistributed here. Customer-facing demos must replace with licensed art before public showing.

## Status

Implemented in `072c8b1` — sidebar bumped from `v0.5.0` → `v0.7.0` simultaneously.

Verified deployment: web task-def 33 (later 36), sidebar shows AWS by default, click cycles through 4 presets.

## See also

- `web/components/CompanyLogo.tsx` — implementation
- `web/components/Sidebar.tsx` (header layout)
- `web/public/logos/README.md` — operator's guide for adding a custom brand
