# Security

Scope: the v1 AP invoice-extraction slice as built. This documents
the threat model, the controls in place, what is deferred, and the trigger that
moves a deferred control in.

## Threat model

The untrusted input is the vendor-supplied invoice text (`invoice_pdf_text`). A
vendor (or whoever controls the document) can plant instructions in the text to try
to subvert the extraction, or send malformed content to break parsing or arithmetic.
The trust boundary is the gateway `/invoke` call: everything inside the prompt
template and the model config is operator-controlled; the variable values are not.

The principal risks:

- **Prompt injection**: text in the invoice that tries to override the system
  instructions (for example "ignore previous instructions and ...").
- **Output integrity**: a model that returns a structurally valid object whose
  arithmetic does not hold, or that does not match the schema at all.
- **Secret exposure**: provider API keys leaking into logs, the repo, or container
  environments.
- **Data exposure**: invoice PII (vendor tax IDs, bank details) in traces or logs.

## Controls in place (v1)

- **Input-side, prompt injection**: a deterministic regex check
  (`gateway/src/releaseplane_gateway/policies/prompt_injection.py`). The patterns
  are stored in the policy bundle (`invoice_v1`), not hard-coded, so coverage is
  tuned as data. A committed test asserts no benign invoice in the 30-case set
  trips the patterns, and that a planted injection is caught. A hit emits a
  `policy_event`; the bundle severity mode decides whether the request is marked
  `failed` (enforce) or only `monitored`.
- **Output-side, schema validity**: the model output is validated against the
  release's JSON Schema (`policies/schema_validity.py`).
- **Output-side, arithmetic consistency**: the shared predicate
  (`releaseplane_shared.arithmetic`) checks the invoice identities within +/-0.01;
  the same predicate gates promotion in the eval harness (ADR 0004, ADR 0006).
- **No content transformation at v1**: a policy failure is recorded
  (`policy_events`, `policy_status` on the response, Grafana), but the output object
  is never modified. The downstream ERP integration decides whether to halt a post
  or queue for human review.
- **Secrets**: provider keys are file-mounted (`*_API_KEY_FILE`), never set as
  environment values in compose and never committed; see `infra/secrets.md`. CI
  runs `detect-private-key` on every change, and a grep guard fails the build if any
  test reaches `api.anthropic.com` or `api.openai.com`.

## PII inventory

AP invoices carry vendor names, addresses, tax/registration IDs, bank account and
routing details, and line-item descriptions. At v1 this data flows through the
gateway and appears in the model call. It is not redacted. Traces record release
identity, token counts, latency, cost, routing decision, and policy status; they do
not record the invoice text or the extracted PII fields. Policy event detail is the
check's evidence (for example which arithmetic identity failed, or which injection
pattern matched), not the invoice content.

## Deferred and the trigger to move it in

- **Injection classifier**: the regex filter is v1. A learned classifier is deferred
  behind a measured trigger: it moves in when the regex filter's false-negative rate
  on a labeled injection set, or a missed live injection, justifies the added cost
  and latency. Until then the patterns are extended as data in the bundle.
- **PII redaction** beyond injection filtering, **RBAC** on the admin UI and the
  promotion API, **audit-log retention** policy, and **signed policy bundles** are
  out of scope for v1 (see `docs/SCOPE.md`) and follow the same no-drift phase-out
  rule.

## Public repository

The repository is going public. Two properties keep that safe, and CI enforces both on
every run so neither can regress silently.

- **No secret is committed, ever.** Provider keys and the dev-stack passwords are
  file-mounted at runtime (`*_API_KEY_FILE`, the files under `infra/secrets/`), never
  set as environment values in compose and never checked in. `.gitignore` covers
  `infra/secrets/*` (keeping only the `.gitkeep` placeholder) and `.env`, and a test
  asserts that coverage so it cannot be removed unnoticed. A `secret-scan` CI job runs
  gitleaks over the full commit history on every push and pull request, so a key added
  in any commit fails the build. Before the flip to public, every key that ever touched
  the repository or the build host is rotated, including the one key used for the single
  gated cost probe.
- **No cross-project or internal reference leaks into new work.** A brand-guard check
  runs over every tracked file, in pre-commit and again as a standalone CI step, and
  fails on the cross-project brand token or the external Knowledge Base path that the
  as-built doc pass removed. Naming the harness in its own documented config stays
  allowed; the guard targets only those two tokens. This covers the working tree and
  every new commit, so the neutralization cannot regress.

Those two tokens still exist in early commit history, from before the as-built pass, so
the working-tree guard is not sufficient on its own for the public flip. Two pre-flip
gates cover history: the gitleaks `secret-scan` job (secrets), and a manual brand-history
scan the owner runs, `python tools/brand_guard.py --history`, which fails while any early
commit still carries a token. The flip to public is gated on scrubbing that history (a
history rewrite, then a force-push) so a clone of the public repo carries neither token
in any commit. Until that scrub, `--history` reports the exact commits and paths to fix.

## Public demo surface

Two things are publicly reachable: Grafana and the Jaeger trace-search UI, both served
through the host's reverse proxy. That reverses the earlier recorded-only decision; ADR
0009 records why.

Everything else is unreachable from outside the host. The control-plane API, the gateway
`/invoke`, Postgres, MinIO, Prometheus, and the OTel collector are published on
`127.0.0.1` by `infra/docker-compose.demo.yml`, so there is no public request path to
them and no public spend surface. The dashboards read data from one prior owner-run
population pass; no visitor action causes a provider call, so there is nothing to
rate-limit or kill-switch. A public **write** endpoint stays out of scope for the
original reasons (`docs/SCOPE.md`): it would need a per-request rate limit, a daily spend
cap with a counter, and an environment kill switch first.

The proxy forwards the whole Grafana surface, not a chosen subset of paths, so anything
Grafana serves is public apart from the five paths refused below. That makes Grafana's own authentication part of the boundary
rather than something behind it. Left on, it would put a working credential oracle on the
internet: `POST /login` answers 200 on the right password and 401 on the wrong one.
Grafana OSS does lock a user out after five failed attempts
(`disable_brute_force_login_protection` defaults to false), which bounds guessing one
known account but not enumeration across accounts, and nothing rate-limits by source. The
demo overlay therefore turns authentication off entirely,
`GF_AUTH_DISABLE_LOGIN_FORM` and `GF_AUTH_BASIC_ENABLED`, so read-only is a property of
the configuration rather than a claim about what a visitor bothers to try. Verified on the
pinned image: `POST /login` returns 400 whatever the password, and basic auth with the
correct admin password returns 401 on a read and 403 on a write. One path those switches
do not cover: a service-account API token authenticates independently of both, so none is
ever minted on this instance. Admin sessions are a second consideration. The
`grafana_data` volume persists across bring-ups, so a session created during an admin
window outlives it; log out at the end of one rather than closing the tab, and treat the
volume as carrying credentials.

Administering Grafana layers `infra/docker-compose.admin.yml` on top of the demo overlay
(`make demo-admin`) rather than dropping it. Dropping it would republish every port on
`0.0.0.0` for the length of the session, trading one password-gated login for an
unauthenticated control-plane API, Postgres, MinIO, Prometheus, Jaeger, and both OTLP
ports. The admin overlay does two things: it reopens the login, and it moves Grafana to
`127.0.0.1:3001`. The second is what makes the first safe. The vhost forwards
`127.0.0.1:3000` unconditionally and cannot know a session is in progress, so a login
form left on that port would be public for the length of it. Moving the instance means
the vhost's upstream is dead and the public URL answers 502 instead. The owner reaches
`3001` over an SSH tunnel; the admin password stays mounted from its secret file in the
base, unreachable rather than removed. A guard asserts the admin overlay never binds the
proxied port.

What an anonymous visitor can do is read every provisioned dashboard, issue read-only
PromQL through Grafana's datasource proxy, and list the datasource itself
(`GET /api/datasources` returns 200 and discloses `http://prometheus:9090`, an internal
compose hostname that resolves nowhere outside the stack). That is accepted: the
datasource is Prometheus only, Postgres is not a Grafana datasource, and Prometheus runs
without `--web.enable-admin-api` and without `--web.enable-lifecycle`, so the proxy
cannot reach a mutating endpoint. Single-query cost is bounded by `--query.timeout` and
`--query.max-samples`; the aggregate is not, since nothing rate-limits the datasource
proxy, so the residual risk is compute exhaustion on an idle box rather than data
exposure. Each vhost writes an access log, so that risk is at least observable and
attributable. Spans carry ids, model, tokens, cost, and policy counters, not invoice
text, so the Jaeger UI exposes release identity rather than customer data.

Write paths were probed against the pinned image rather than assumed.
`POST /api/dashboards/db`, `/api/annotations`, `/api/datasources`, `/api/library-elements`,
and `/api/admin/settings` return 403; `/api/snapshots` returns 401; `/api/playlists`
returns 403 on a well-formed body. External snapshot sharing is switched off, so nothing
can post dashboard data to a third-party host.

The Viewer role covers the endpoints that check a role. It does not cover the ones that
only check whether a request is signed in, because Grafana counts an anonymous visitor
as signed in. Four were reachable, each measured rather than assumed, and all four are
refused at the reverse proxy (`infra/caddy/releaseplane.Caddyfile`) with a 405:

| Path | Was | Why it matters |
| --- | --- | --- |
| `POST /api/short-urls` | 200 | Wrote a row that `/goto/<uid>` then resolved. Small, but unbounded and uncredentialed. The trailing-slash form answered too, and Caddy's path matcher is exact, so both are listed. |
| `GET /api/gnet/*` | 200 | Grafana's proxy to grafana.com. A visitor could make this box originate outbound requests. |
| `POST /api/frontend-metrics` | 200 | Anonymous data written into the instance. |
| `POST /api/live/publish` | 400 | Reached body validation rather than an authorization refusal, so authorization was not the thing stopping it. |

Read-only on this surface is therefore two mechanisms, Grafana's roles and the vhost's
refusals, and the second is part of the boundary rather than plumbing in front of it.
That is also why there is no blanket method rule: `POST /api/ds/query` is what renders a
panel, so refusing non-GET would break the dashboards it was protecting. The rest of
Grafana passes through, including the `/api/live/ws` the frontend opens.

Two operational notes carry real weight here.

**The loopback bind is the control that holds, not the firewall.** Docker's DNAT rules
sit in the nat table ahead of the filter rules ufw manages, so unless a host wires an
explicit `DOCKER-USER` rule, ufw does not gate a published container port at all. On the
demo host it does not, and before the loopback rebind the control plane answered on the
public IP directly. Treating the firewall as a second layer behind the bind would be
wrong; there is one layer, and the check that it holds is run from a client outside the
host, never from localhost. Any host running this stack on a public address should
assume the same and verify the same way.

**Grafana is kept current, not merely pinned.** Serving it anonymously on the public
internet changes its patch posture. CVE-2025-3260 was an authorization bypass in the
dashboard API that named anonymous-auth instances specifically, so the pinned digest
moves forward with upstream releases rather than staying where it was first set. That is
a standing obligation, so it has a mechanism behind it rather than a promise:
`.github/dependabot.yml` watches the compose images weekly and opens a pull request that
moves the digest and names the release. Digests stay pinned, so an upgrade is still a
reviewed commit.
