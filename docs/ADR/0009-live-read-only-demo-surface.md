# ADR 0009: The public demo is a live read-only observability surface

Date: 2026-07-23
Status: Accepted. Reverses D-DEMO-ENDPOINT (recorded-only) from Phase 6.

## Context

Phase 0 locked the demo as a recording against the local stack, and `docs/SCOPE.md`
put a hosted public demo URL out of scope for v1. The reasoning was specific and
still holds for what it addressed: a public endpoint that reaches the gateway would
need a per-request rate limit, a daily spend cap with a counter, and a kill switch
before it could be safe, and none of that carries the narrative.

That reasoning was about a public **write** path. It was applied to the whole idea of
a hosted URL, which is broader than the risk it describes. After the RUNBOOK
walkthrough ran end to end and the stack proved demo-ready, the question came back:
the eval gate blocking v1 and passing v2 is the project's headline, and a reader who
can click it is in a different position from one who watches a recording of it.

The observability plane already holds that story in a form with no write path.
Grafana reads Prometheus. Jaeger reads spans. Neither can create a release, promote
one, or reach a provider.

## Decision

The public demo is Grafana and Jaeger, served read-only through the reverse proxy
that already fronts the host's other demos. Grafana runs anonymous with the Viewer
role and opens on the eval dashboard. Jaeger serves trace search on a second vhost.

Nothing else is publicly reachable. The control-plane API, the gateway `/invoke`,
Postgres, MinIO, Prometheus, and the OTel collector are bound to loopback and are
reached only by the proxy or from the host itself.

The data behind the dashboards is real and comes from one owner-run population pass,
not from live traffic. Visitors read pre-computed results; no visitor action causes a
provider call.

The recorded walkthrough stays. It is the narrated artifact and carries the argument;
the live dashboard is the clickable companion to it.

## Rationale

- The exposed surface has no write path at all, so the three controls SCOPE named as
  preconditions (rate limit, spend cap, kill switch) guard a risk that this shape does
  not create. A live **write** endpoint stays out of scope for exactly the original
  reasons.
- Anonymous Viewer cannot edit, create, delete, or sign up. It can issue read-only
  PromQL through Grafana's datasource proxy, which reads counters and rates. Postgres
  is not a Grafana datasource, so invoice content is not reachable that way. Spans
  carry ids, model, tokens, cost, and policy counters, not invoice text
  (`docs/SCOPE.md`, observability line).
- The boundary is enforced by binding rather than by configuration a reader has to
  trust. Every non-public service is published on `127.0.0.1` in
  `infra/docker-compose.demo.yml`, and the check that it held is run from outside the
  host, not from localhost.

## Consequences

- `infra/docker-compose.demo.yml` is opt-in and inert unless named on the compose
  command line, so the committed base never enables anonymous access and a plain
  bring-up is unchanged.
- A host firewall is not a second layer here. Docker's DNAT rules sit in the nat table
  ahead of the filter rules ufw manages, so unless the host wires a `DOCKER-USER`
  rule, ufw does not gate a published container port at all. The loopback bind is the
  control that holds, and the runbook says so rather than implying defense in depth
  that is not present.
- Grafana is now internet-facing with anonymous auth, which changes its patch posture
  from "pinned" to "kept current". CVE-2025-3260 was an authorization bypass in the
  dashboard API that named anonymous-auth instances specifically, so the pin moves
  forward with releases rather than staying where it was first set.
- The demo data must outlive the run that produced it. Prometheus gets a data volume
  with matching retention, and the demo-facing dashboards open on a wide time range.
  The control-plane counters still live in that process and Jaeger holds traces in
  memory, so a restart of either costs part of the picture; `docs/RUNBOOK.md` states
  that limit rather than claiming the surface is restart-proof.
- `docs/SCOPE.md` and `docs/SECURITY.md` are updated to match. This ADR is the record
  that the earlier decision was made, held for a reason, and then changed.
