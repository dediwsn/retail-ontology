# Security posture — explicit demo trade-offs and production migration plan

This document records security decisions that an automated reviewer (Kiro)
correctly flagged as gaps, with the rationale for the demo posture and the
exact migration path for production cutover.

Items that have since been closed are marked **Resolved** rather than deleted,
so the decision log stays readable as a history. Last verified against the
codebase on **2026-08-31**.

## 1. CloudFront ↔ ALB unencrypted (HTTP:80)

**Current**: ALB listener is HTTP on port 80. CloudFront origin protocol
policy is `HTTP_ONLY`. Traffic between CF edge POPs and the ALB origin is
not TLS-encrypted.

**Spec reference**: § 5.3 — *"데모 단계는 ALB 리스너 80(HTTP). CloudFront ↔
ALB 구간은 AWS 백본 + Origin Shield(선택)로 보호. 운영 단계는 ACM + ALB
:443으로 격상."*

**Defenses currently in place**:
- ALB Security Group restricts ingress to the AWS-managed CloudFront
  origin-facing prefix list (`com.amazonaws.global.cloudfront.origin-facing`).
  Direct internet→ALB is impossible.
- Org compliance (`Epoxy`) auto-deletes ALB listeners that have any
  `0.0.0.0/0` ingress, enforcing this prefix-list-only posture
  (commit `560844b`: addListener `open: false`).
- **Origin token enforced today.** `ComputeStack` sets
  `REQUIRE_ORIGIN_AUTH: 'true'` on the API task definition
  (`infra-cdk/lib/compute-stack.ts`), so `AuthMiddleware` rejects any request
  arriving without a matching `X-Origin-Auth-Token`. CloudFront injects it as
  a custom origin header resolved at deploy time from Secrets Manager
  (`{{resolve:secretsmanager:...}}` — the CFN template carries the directive,
  never the plaintext). Comparison is `hmac.compare_digest`, so it is
  constant-time. This is defense-in-depth over the plaintext CF→ALB hop, not
  the only line.

**Why HTTPS isn't enabled in the demo**:
- ALB HTTPS requires an ACM certificate.
- Public ACM certs require ownership of a domain (DNS validation).
- *.elb.amazonaws.com is AWS-owned, so we can't get a public cert for it.
- Self-signed certs work for ALB but **CloudFront refuses to validate
  self-signed origin certificates** — origin protocol must be HTTPS_ONLY
  with a chain CF accepts.
- ACM Private CA solves this but costs ~$400/mo — disproportionate for
  a demo.

**Production migration**:
1. Acquire/assign a custom domain (e.g., `demo.example.com`).
2. Issue ACM cert in us-east-1 for the CF distribution alias.
3. Issue ACM cert in ap-northeast-2 for the ALB (covering the ALB's
   custom domain entry, e.g., `origin-demo.example.com`).
4. CDK changes:
   - `EdgeStack`: add `aliases` + `certificate` to `cloudfront.Distribution`.
   - `ComputeStack`: add 443 listener with the seoul ACM cert; redirect 80→443.
5. Set `REQUIRE_ORIGIN_AUTH=true` permanently to keep the layered defense.

## 2. Edge auth enforced; API JWT check opt-out by default

> **Updated 2026-08-31.** This section previously described the Lambda@Edge
> function as an inline pass-through and the API-side JWT check as structural
> only. Both statements are obsolete — see ADR-0012 and
> `api/middleware_auth.py:_verify_jwt`. What remains open is narrower than
> what this document used to claim.

**Current**: authentication is enforced **at the CloudFront edge**, before any
request reaches the origin. The API-side JWT check is fully implemented but
still defaults to bypass via `DEMO_PUBLIC_MODE`.

### 2.1 Lambda@Edge — implemented (not a pass-through)

`AuthEdgeFn` (`infra-cdk/lib/edge-stack.ts`, `us-east-1` via
`cfExperimental.EdgeFunction`) runs on **viewer-request** for every request to
the distribution and does the following:

1. Returns the request unchanged if the URI matches `PUBLIC_PATHS`. That list
   is deliberately narrow:
   `[/api/auth/callback, /api/auth/logout, /_next/, /favicon, /api/health]`.
   **The root path `/` is gated** — an anonymous browser's first network
   response is a 302, not a half-rendered SPA shell. See
   [ADR-0012](docs/decisions/0012-lambda-edge-root-gate-and-logout.md).
2. Reads the `id_token` and `access_token` cookies from the request headers.
3. Accepts the request if either token is structurally well-formed (three
   segments) and carries a numeric `exp` claim in the future.
4. Otherwise returns a `302` to the Cognito Hosted UI `/oauth2/authorize`
   endpoint with `response_type=code`, `scope=openid+email+profile`, and a
   `redirect_uri` **derived from the request `Host` header** — so the function
   adapts to any alias without a redeploy.

The Cognito domain and app-client ID are baked into the function source at
synth time by string substitution, because Lambda@Edge supports neither
environment variables nor CDK tokens here (a forward reference to the user-pool
client would create a synth cycle through the distribution). See
[ADR-0003](docs/decisions/0003-lambda-edge-stable-id-hardcode-strategy.md).

**Deliberate scope**: the edge check validates *presence and expiry*, not the
RS256 signature. This is the user-flow gate. Cryptographic verification is the
API's job, and the API does it — see 2.2. Splitting it this way keeps the edge
function small and its cold-start negligible; a forged-but-well-formed cookie
gets past the edge and is then rejected at the API whenever
`DEMO_PUBLIC_MODE=false`.

**Session teardown**: `/api/auth/logout` clears all three token cookies *and*
redirects to the Cognito Hosted UI logout URL, so logout ends the IdP session
rather than only the local one. The Cognito app client must list
`https://<PUBLIC_DOMAIN>/` (with the trailing slash) as a LogoutURL.

### 2.2 API-side JWT verification — implemented, bypassed by default

`api/middleware_auth.py:_verify_jwt` performs **full RS256 verification** via
PyJWT + `cryptography`:

- signature verified against the JWK matched by `kid` from Cognito's JWKS
  endpoint (`RSAAlgorithm.from_jwk`),
- `iss` checked against the expected
  `https://cognito-idp.<region>.amazonaws.com/<user-pool-id>`,
- `exp` / `nbf` validated by PyJWT,
- audience checked manually as `client_id` (access tokens) or `aud`
  (id tokens), because Cognito access tokens carry no `aud` claim,
- JWKS cached in a `TTLCache(maxsize=4, ttl=3600)` — a 1-hour TTL rather than
  `lru_cache`, so key rotation cannot permanently reject freshly-signed tokens.

**The remaining gap** is the switch, not the implementation:
`AuthMiddleware.dispatch` reads `os.environ.get("DEMO_PUBLIC_MODE", "true")`
and skips the JWT branch when it is `true`. `ComputeStack` does not set the
variable, so the deployed API defaults to **public mode**. Origin-token
enforcement (§1) still applies in that state, so the API is reachable only
through CloudFront — but any CloudFront visitor reaches it without a valid
token.

Note also that `_is_public` exempts every path under `/api/auth/` in addition
to `/healthz` and `/api/health-web`. That is required for the OAuth round trip
and is intentional, but it means those routes are unauthenticated by design in
both modes.

**Why the bypass is still in place**:
- The demo is invitation-only behind a known URL, and the edge gate already
  keeps anonymous browsers out of the UI.
- The application stores no user-identifying data — synthetic personas only.
- `scripts/eval_wow_queries.py` and the offline pytest suite both rely on the
  public mode to run without a session cookie (`tests/conftest.py` sets
  `DEMO_PUBLIC_MODE=true` at collection time).

**Migration to fully enforced auth**:
1. Provision real users: `scripts/provision_cognito_users.sh` creates the demo
   accounts with temporary passwords and group membership
   (`shopper` / `md` / `admin`).
2. Set `DEMO_PUBLIC_MODE: 'false'` in the API task-definition environment block
   in `infra-cdk/lib/compute-stack.ts`, then `cdk deploy compute` and force a
   new deployment. No application code changes.
3. Give the evaluation harness a session cookie (`--cookie`) instead of relying
   on public mode — see `.claude/skills/wow-query-eval.md`.
4. *Optional hardening*: promote the edge check from structural to full
   signature verification with the `cognito-at-edge` package. Only worth doing
   if the edge must reject forged tokens on its own; with 2 in place, the API
   already rejects them.
5. Consume Cognito group claims for route-level authorisation. Groups are
   provisioned but not yet enforced anywhere — this is the real remaining work,
   not the JWT plumbing.

## 3. Other accepted demo trade-offs (P1 backlog)

- **CloudWatch Logs CMK**: removed customer-managed key encryption
  due to cross-stack KMS cycle. Currently AWS-managed CMK
  (commit `9469251`). Production fix: relocate LogGroups to DataStack
  (where the KMS key lives) so the cycle disappears.
- **CloudTrail Bedrock data events**: not enabled. Compliance audit
  trail for Bedrock model invocations is missing. Production fix:
  add `CfnTrail` with EventSelectors for
  `AWS::Bedrock::ModelInvocation` in ObservabilityStack.
- **ALB access logs to S3 with 30-day retention**: not enabled. Production
  fix: `accessLogs.bucket` on ALB construction in ComputeStack pointing
  to a new dedicated S3 bucket in DataStack.
- ~~**AWS Cost Anomaly Detection**: not enabled.~~ **Implemented** —
  `ObservabilityStack` attaches a `ce.CfnAnomalySubscription` to the account's
  `Default-Services-Monitor` with email notification.

The remaining items are tracked in spec § 10/§ 11.2 and are blocked on
nothing technical — they're ~1 hour of CDK work each and were deprioritized
behind getting the wow scenarios working end-to-end.

## Decision log

| # | Issue | Severity (Kiro) | Demo posture | Migration trigger |
|---|---|---|---|---|
| 1 | CF↔ALB plaintext | HIGH | Accepted, prefix-list-only SG + `X-Origin-Auth-Token` enforced | Custom domain assigned |
| 2 | Edge auth no-op | HIGH | **Resolved** — Lambda@Edge gates every path incl. `/`, 302s to Cognito (ADR-0012) | n/a |
| 3 | API auth bypass | HIGH | Open — full RS256 verification implemented, gated behind `DEMO_PUBLIC_MODE` (default `true`) | Cognito users provisioned |
| 3b | JWT verified structurally only | HIGH | **Resolved** — full RS256 + JWKS + iss/exp/aud in `_verify_jwt` | n/a |
| 4 | Logs AWS-managed key | MED | Accepted, encryption still active | Production deployment |
| 5 | No CT data events | MED | Accepted, deferred | Compliance audit requirement |
| 6 | No ALB access logs | MED | Accepted, deferred | Forensics need |

Tracked: `~/.claude/projects/.../memory/agentcore_gotchas.md` and this file.
