# ADR-0012: Root-path Cognito gate + /api/auth/logout

- Status: Accepted
- Date: 2026-05-09
- Deciders: @whchoi98
- Tags: auth, lambda-edge, cognito, ux

## Context

Through v0.7.0 the Lambda@Edge `PUBLIC_PATHS` regex list at `infra-cdk/lib/edge-stack.ts` included `/^\/$/`, which let anonymous browsers load the React shell at `https://retail-ontology.whchoi.net/` *without* hitting Cognito. The redirect only fired later when the first authenticated API call (e.g. `/api/whoami`) returned 401 and the client interpreted it as a re-login signal. Result: anonymous users saw a half-rendered, stuck home page and only got bounced to Cognito after the SPA was already running — divergent from `mfg-ontology` (which gates the root path) and confusing as a demo experience.

Two related gaps surfaced at the same time. There was no `/api/auth/logout` endpoint, so the sidebar logout link sent users to the Cognito Hosted UI logout but our `id_token` / `access_token` / `refresh_token` cookies stayed set — clicking "logout" did not actually log the user out of *this* application on the next visit. And `/api/auth/whoami` raised `HTTPException(401)` for unauthenticated callers, forcing the `SidebarAuth` widget to treat the normal "logged out" state as an error and emit noisy console traces.

## Decision

We tighten the auth surface to match the `mfg-ontology` pattern: the root path is auth-gated like every other page, an explicit `/api/auth/logout` endpoint clears cookies *and* bounces to the Cognito Hosted UI logout URL, and `/api/auth/whoami` always returns JSON 200 — `{authenticated: true|false}` — so the client can render the unauthenticated state as a normal UI branch instead of an error.

## Alternatives Considered

- **Keep `/^\/$/` in PUBLIC_PATHS (status quo)** — Rejected: divergent from `mfg-ontology`, confusing UX (half-loaded shell), and leaves the root URL as the only place where the auth contract is "client races itself to a Cognito redirect" instead of "edge gate enforced".
- **Whoami returns 401 for unauthenticated** — Rejected: forces every consumer to treat a routine state ("nobody is logged in yet") as an error, leading to noisy fetch error logs and entanglement with retry/backoff layers that don't apply here.
- **Replace Lambda@Edge with an API Gateway authorizer** — Rejected: would break static-asset cacheability through CloudFront, require restructuring every route, and gain nothing for this demo's threat model. Lambda@Edge cookie validation is sufficient.

## Consequences

### Positive

- Root URL behavior matches the rest of the application (and `mfg-ontology`) — first network request from an anonymous browser is a 302 to Cognito.
- Logout actually logs out: `delete_cookie` for all three tokens *plus* Cognito Hosted UI logout invalidates the IdP session.
- `whoami` becomes a clean state probe; `SidebarAuth` renders three explicit branches (loading / unauthenticated / authenticated) without error pathways.

### Negative

- Every fresh viewer pays one extra Lambda@Edge invocation before reaching Cognito (negligible cost; <10ms p99).
- Tests or scripts that previously curled `/` anonymously and got HTML back now get a 302 — they must either follow redirects (`-L`) or set the `id_token` cookie. `scripts/eval_wow_queries.py` already handles this via `DEMO_PUBLIC_MODE`.

### Neutral

- `PUBLIC_PATHS` shrank to `[callback, logout, _next, favicon, api/health]`. Any future addition must be deliberate — adding too generous a regex is the most likely way to silently regress this decision.

## Implementation Notes

- Files touched:
  - `api/routers/auth.py` — new `auth_logout()` endpoint, `auth_whoami()` returns JSON 200 instead of raising 401.
  - `infra-cdk/lib/edge-stack.ts` — `PUBLIC_PATHS` regex list trimmed.
  - `web/components/SidebarAuth.tsx` — already tolerant of JSON `authenticated:false`; no change required.
- Cognito App Client must list `https://<PUBLIC_DOMAIN>/` (with trailing slash) as a LogoutURL — the logout endpoint redirects to that exact URL.
- Lambda@Edge replication takes ~30s globally after `cloudfront update-distribution`; verify with `curl -I https://retail-ontology.whchoi.net/` returning `HTTP/2 302` and `location: …cognito…`.
- Rollback: re-add `/^\/$/` to PUBLIC_PATHS and revert the auth router changes. Logout endpoint can stay (independent of the root gate).

## References

- Commit `64fa25a fix(auth): match mfg pattern — root path triggers Cognito + add logout`
- ADR-0003 — Lambda@Edge stable ID strategy (adjacent concern; deals with deploying the function, not which paths it gates)
- `mfg-ontology` `/api/auth/*` (pattern source)
