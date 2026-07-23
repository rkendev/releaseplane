# Runbook

How to bring up the ReleasePlane local dev stack and get green health checks
from a clean clone, plus the failure modes you are most likely to hit.

## Prerequisites

- Docker Engine and the Docker Compose plugin (`docker compose version`).
- For running tests and lint locally: `uv` (`uv sync` installs everything).
- `jq`, for the release walkthrough below.

## 1. Create local secrets

The stack reads passwords from files in `infra/secrets/` (never committed).

```bash
cp infra/.env.example .env     # then edit .env and set the passwords
make secrets                   # writes infra/secrets/* from .env
```

`make secrets` writes world-readable dev files so the non-root service
containers (for example Grafana, uid 472) can read them. Production uses a
separate `0400` path; see `infra/secrets.md`.

## 2. Bring up the stack

```bash
docker compose -f infra/docker-compose.yml up -d
```

This starts Postgres, MinIO, the OpenTelemetry Collector, Jaeger, Prometheus,
Grafana, and builds and starts the `control-plane` and `gateway` services. The
app services wait for their dependencies to report healthy.

## 3. Check health

```bash
curl http://localhost:8001/healthz   # control-plane
curl http://localhost:8002/healthz   # gateway
```

Expected:

```json
{"status": "ok", "service": "control-plane", "db": true}
{"status": "ok", "service": "gateway"}
```

`db: true` means the control plane reached Postgres on startup. `db: false` with
a 200 response means the process is live but could not connect (see below).
`docker compose -f infra/docker-compose.yml ps` shows each container's health.

## Before a demo: rebuild and migrate

Two states bite a demo bring-up that a plain `up -d` does not fix on its own.

First, `up -d` reuses a cached image even when the source has moved on, so a
service can run an older build that is missing newly wired routes. Rebuild the
app services from current source before the demo:

```bash
docker compose -f infra/docker-compose.yml build control-plane gateway
docker compose -f infra/docker-compose.yml up -d
```

On a host that remaps ports through a local override, add
`-f infra/docker-compose.override.yml` to both commands (see Port already in use
under Common failure modes).

Second, migrations do not run on container startup, so the persisted Postgres
volume can lag the latest Alembic revision; a missing table surfaces as a 500
from the matching endpoint. Apply them once the stack is healthy:

```bash
make migrate            # add PGPORT=5433 if a local override remaps Postgres
```

## Walk a release through the gate

Seeding registers prompts, not releases. This is the full path from a seeded stack to an
active release. It assumes `jq` and the host ports the committed compose publishes.

```bash
CP=http://localhost:8001
GW=http://localhost:8002

# 1. Policy bundle invoice_v1 plus prompt versions v1 and v2. Idempotent.
CONTROL_PLANE_URL=$CP uv run python control-plane/scripts/seed_invoice_v1.py

# 2. Model config, seeded from infra/model_configs/v1_default.yaml. Idempotent.
curl -s -X POST $CP/model-configs/seed > /dev/null

# 3. Collect the three ids a release binds.
PROMPT_ID=$(curl -s $CP/prompts | jq -r '.[] | select(.name=="invoice-extraction") | .id')
VERSION_ID=$(curl -s $CP/prompts/$PROMPT_ID/versions | jq -r '.[] | select(.version=="v2") | .id')
MODEL_ID=$(curl -s $CP/model-configs | jq -r '.[] | select(.name=="v1_default") | .id')
BUNDLE_ID=$(curl -s $CP/policy-bundles | jq -r '.[] | select(.name=="invoice_v1") | .id')

# 4. Create the release. It starts in draft.
RELEASE_ID=$(curl -s -X POST $CP/releases -H 'content-type: application/json' \
  -d "{\"prompt_version_id\":\"$VERSION_ID\",\"model_config_id\":\"$MODEL_ID\",\"policy_bundle_id\":\"$BUNDLE_ID\"}" \
  | jq -r .id)

# 5. Load the 30-case golden dataset.
CONTROL_PLANE_URL=$CP uv run python -m releaseplane_evals.cli load
DATASET_ID=$(curl -s $CP/eval-datasets | jq -r '.[] | select(.name=="invoice_v1") | .id')

# 6. Score the release. The runner pins the release by id, so it scores this
#    release's own model config and never routes.
CONTROL_PLANE_URL=$CP GATEWAY_URL=$GW \
  uv run python -m releaseplane_evals.cli run --release-id $RELEASE_ID --dataset-id $DATASET_ID

# 7. Promote. Two hops: draft to candidate, candidate to active. The gate runs on both.
curl -s -X POST $CP/releases/$RELEASE_ID/promote | jq .
curl -s -X POST $CP/releases/$RELEASE_ID/promote | jq .
```

Both CLI commands need their URLs passed explicitly: the evals CLI defaults to port 8000,
which is the in-container port, not the host-published one.

On the default dev stack the gateway is pinned to `DummyProvider`, which returns a canned
object rather than calling a model. Step 6 therefore scores 0 percent on schema validity
and step 7 returns:

```
409  {"detail": "promotion blocked: tier 1 schema_validity 0% < 100%; ..."}
```

That is the gate working, at zero spend. Reaching an active release needs a real provider,
which is a deliberate operator step: bring the gateway up with a provider key and
`GATEWAY_PROVIDER=claude`, re-run step 6, then promote. Once a release is active,
`POST $GW/invoke` resolves it by prompt name:

```bash
curl -s $GW/invoke -H 'content-type: application/json' \
  -d '{"prompt_name": "invoice-extraction", "variables": {"invoice_pdf_text": "..."}}' | jq .
```

## CLI and curl side by side

The `releaseplane` console CLI (from the `sdk` package) wraps the read and promote calls
above, so the demo can show one clean line instead of a curl-and-jq pipe. Each verb is a
single control-plane call and nothing more; curl stays the honest fallback. Point the CLI
at the control plane with `--url` (accepted before or after the verb) or the
`RELEASEPLANE_URL` environment variable.

| Operation | CLI | curl |
| --- | --- | --- |
| List prompts | `releaseplane prompts list` | `curl -s $CP/prompts` |
| List releases | `releaseplane releases list` | `curl -s $CP/releases` |
| Promote a release | `releaseplane releases promote <id>` | `curl -s -X POST $CP/releases/<id>/promote` |
| Latest eval run | `releaseplane eval status --release-id <id>` | `curl -s "$CP/eval-runs?release_id=<id>"` |

```bash
export RELEASEPLANE_URL=$CP
releaseplane releases list
releaseplane eval status --release-id $RELEASE_ID
releaseplane releases promote $RELEASE_ID   # prints the 409 reason on one line, exits 1
```

`releases promote` is the one to show: on a blocked release it prints the gate reason
(`promotion blocked: tier 1 schema_validity 0% < 100%; ...`) on a single line and exits
non-zero, rather than dumping a JSON body. The CLI reports no gate verdict of its own; the
thresholds live in the control plane, and the CLI only surfaces what the API returns.

Executing an eval run is not a CLI verb: use the evals harness directly, which is the
`run` step in the walkthrough above:

```bash
CONTROL_PLANE_URL=$CP GATEWAY_URL=$GW \
  uv run python -m releaseplane_evals.cli run --release-id $RELEASE_ID --dataset-id $DATASET_ID
```

## Service URLs

| Service | URL | Notes |
| --- | --- | --- |
| control-plane | http://localhost:8001/healthz | health; `/metrics` for Prometheus |
| gateway | http://localhost:8002/healthz | health; `/metrics` for Prometheus |
| Grafana | http://localhost:3000 | login `admin` / `GRAFANA_ADMIN_PASSWORD` from `.env` |
| Jaeger | http://localhost:16686 | trace search |
| Prometheus | http://localhost:9090 | `/targets` shows scrape health |
| MinIO console | http://localhost:9001 | object store |

Traces flow from the services to the collector and on to Jaeger. Metrics are
scraped by Prometheus and shown in Grafana (the Prometheus datasource is
provisioned at boot).

## Read-only demo

The public demo is Grafana and Jaeger only, served through a reverse proxy, showing
data from one prior population run. Nothing a visitor can reach writes state or calls
a provider. The decision and its boundary are recorded in ADR 0009.

### Bring up with the demo overlay

`infra/docker-compose.demo.yml` is opt-in. It is inert unless named on the command
line, so a normal bring-up is unaffected by it. It needs a Compose version that
understands the `!override` merge tag (verified on v5.1.0). An older client fails to
parse the merged config rather than quietly keeping the wide binding, and the `config`
render below is the check that it parsed.

```bash
make demo-config                   # render first; this is where a mistake shows up
make demo-up
make migrate PGPORT=$PG_HOST_PORT  # the port infra/.env publishes, 5432 by default
```

`make demo-up` is the supported bring-up on a public-facing host. Prefer it to a
hand-written compose line every time: a bring-up, rebuild, or restart that forgets
the overlay republishes all ten services on `0.0.0.0`, and the guards in
`tests/test_public_readiness.py` are static checks that cannot catch that at runtime.
The plain `docker compose` commands elsewhere in this runbook and in the README are
for a laptop or a private network.

Before the first public bring-up, confirm the origin resolved:

```bash
make demo-config | grep GF_SERVER_ROOT_URL
```

An unset `DEMO_ROOT_URL` falls back to `http://localhost:3000/`, which sends Grafana's
redirect and share links to the visitor's own machine.

The overlay is last in the `-f` order, so it decides the published ports. It carries
no host's port layout of its own: the numbers come from `PG_HOST_PORT`,
`CONTROL_PLANE_HOST_PORT`, `GATEWAY_HOST_PORT`, `MINIO_HOST_PORT`, and
`MINIO_CONSOLE_HOST_PORT`, defaulting to the base compose ports. A host that remaps
sets them in `infra/.env` (gitignored), which compose reads from the project
directory, and passes the matching `PGPORT=` to `make migrate`. `DEMO_ROOT_URL` sets
the public origin Grafana builds its redirect and share links from. See
`infra/.env.example`.

Check what the merged files actually render before starting anything:

```bash
make demo-config
```

### What is exposed

| Surface | Public | Reached how |
| --- | --- | --- |
| Grafana (anonymous Viewer) | yes | proxy vhost to `127.0.0.1:3000` |
| Jaeger trace search | yes | proxy vhost to `127.0.0.1:16686` |
| control-plane API | no | loopback only |
| gateway `/invoke` | no | loopback only |
| Postgres, MinIO, Prometheus, OTel collector | no | loopback only |

Anonymous Viewer can read every provisioned dashboard and can issue read-only PromQL
through Grafana's datasource proxy. It cannot edit, create, delete, or sign up, and
Postgres is not a Grafana datasource, so no invoice data is reachable that way.
External snapshot sharing is off, so nothing posts dashboard data outbound.

The overlay also turns Grafana's authentication off, both the login form and basic
auth. The proxy forwards the whole service, so a login form on it is a public
credential oracle: Grafana's brute-force lockout bounds guessing one known account,
but nothing rate-limits by source. Nothing here needs runtime administration anyway,
since the dashboards and the datasource are provisioned from files.

**To administer Grafana**, layer the admin overlay on top rather than dropping the
demo one. Dropping it would republish all ten ports on `0.0.0.0` for the length of
the session, which is a far larger hole than the login it reopens:

```bash
make demo-admin
ssh -N -L 3000:127.0.0.1:3000 <user>@<demo-host>
# then http://localhost:3000, admin / GRAFANA_ADMIN_PASSWORD from .env
make demo-up            # back to the public read-only surface
```

Anonymous access is off while the admin overlay is on, so the public URL stops
serving until `make demo-up` puts it back. An instance is either the public surface
or the administered one, not both.

`docs/SECURITY.md` has the full boundary and the probes that confirmed it.

Serving Grafana anonymously on the public internet means keeping it patched rather
than leaving the pin where it was set. Check the vendor advisories before a flip and
move the digest forward.

### Reverse proxy

The demo host fronts with Caddy, which issues and renews the certificates on its own.
Append to `/etc/caddy/Caddyfile`:

```
# >>> releaseplane demo (managed) >>>
releaseplane.<demo-host> {
	reverse_proxy 127.0.0.1:3000
	encode gzip
}

releaseplane-traces.<demo-host> {
	reverse_proxy 127.0.0.1:16686
	encode gzip
}
# <<< releaseplane demo (managed) <<<
```

Substitute the real hostname, the same one `DEMO_ROOT_URL` carries in `infra/.env`.
Each block proxies a whole service rather than a path allowlist, which is why
Grafana's own authentication is switched off in the overlay: everything Grafana
serves is public.

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Two hostnames rather than one host with a `/traces` path: Jaeger needs
`QUERY_BASE_PATH` to serve its UI under a subpath, and a second vhost costs nothing
here.

### The reachability gate

The loopback bind is the control that holds, not the host firewall. Docker's DNAT
rules sit in the nat table ahead of the filter rules ufw manages, so unless the host
wires a `DOCKER-USER` rule, a published container port is reachable on the public IP
whatever ufw says about it. Confirm which way it renders:

```bash
make demo-ports
```

Every port must read `127.0.0.1:`; none may read `0.0.0.0:`. Then check from a client
that is not this host (a laptop, not an SSH session into the box), because a
`localhost` probe passes either way. Every published port goes in the list:

```
# control-plane, gateway, Postgres, Prometheus, Grafana, Jaeger,
# OTLP gRPC and HTTP, MinIO API and console
Test-NetConnection <public-ip> -Port 8001    # and 8002, 5432, 9090, 3000,
                                             # 16686, 4317, 4318, 9000, 9001
```

Substitute the remapped numbers on a host that sets them. Every one must fail. If any
raw port answers, the demo does not go live until it is closed. The two demo URLs are
the only things that may answer.

### Why the dashboards default to a wide time range

The eval and gateway dashboards open on `now-1y`. The eval metrics are emitted once
per run, so a narrow window shows an empty panel the day after a population run.
Prometheus keeps a `prometheus_data` volume with matching retention, capped by size
as well as time, so the samples survive a Prometheus or host restart. The tradeoff is
that the gateway's rate and latency panels are coarse at that range; zoom in for live
use, and leave it wide for the demo.

One limit before restarting anything: the control-plane counters and gauges live in
that process, not in the database. After a control-plane restart the samples already
in the TSDB still render, so the timeseries panels keep the story, but the metrics
themselves are labelled and have no child until the next run, so they are absent from
`/metrics` rather than zero. The "Total eval runs" stat therefore reads no data, not
0, until an eval runs again. Jaeger all-in-one holds traces in memory, so its
container has to stay up for the trace links to resolve. Keep the stack running
between demos rather than cycling it.

## Common failure modes

- **Port already in use** (for example `bind host port 0.0.0.0:5432: address
  already in use`). Another process on the host owns that port. Fix: create
  `infra/docker-compose.override.yml` and republish the service on a free port,
  then add `-f infra/docker-compose.override.yml` to the compose command. Use
  `!override` so the list replaces rather than appends:

  ```yaml
  services:
    postgres:
      ports: !override
        - "5433:5432"
  ```

- **The seed aborts with `SeedDriftError`, or `/invoke` reports
  `"policy_status": "not_applied"`.** Both point at the same stale bundle. A policy
  bundle is immutable and `seed_policy_bundle` matches on `(name, version)`, so a
  persisted volume holding an `invoice_v1@v1` row from before the policy engine landed
  keeps its old `rules_json`. The seeder now refuses to skip silently: if the stored
  bundle differs from the seed (an empty `rules_json`, a `warn` severity), it raises
  `SeedDriftError` naming the difference. And because an empty bundle runs no check, the
  gateway reports `not_applied` with `policy_checks_applied: 0` rather than a vacuous
  `passed`, so the no-op is visible instead of looking clean. Confirm with:

  ```bash
  curl -s http://localhost:8001/policy-bundles \
    | jq '.[] | select(.name=="invoice_v1") | {severity_mode, rules_json}'
  ```

  A current bundle has `severity_mode: "enforce"` and a `rules_json.checks` list of
  `prompt_injection`, `schema_validity`, `arithmetic_consistency`. If yours is empty, the
  row predates the engine. Fix by wiping the volume
  (`docker compose -f infra/docker-compose.yml down -v`, then bring up, migrate, and
  re-seed), which is the safe option on a dev stack. The seed then lands the current
  bundle on the clean volume.

- **Grafana exits with `permission denied` on a secret.** The secret file is not
  readable by the Grafana user. Fix: re-run `make secrets` (it writes `0644`).

- **`db: false` from control-plane.** Postgres is not reachable or the password
  secret is missing. Fix: confirm `infra/secrets/postgres_password` exists
  (`make secrets`) and that the postgres container is healthy, then
  `docker compose -f infra/docker-compose.yml up -d`.

- **Stale volumes** (old database or object data causing odd state). Fix:
  `docker compose -f infra/docker-compose.yml down -v` drops the named volumes,
  then bring the stack back up for a clean slate.

- **Image digest mismatch on pull.** A pinned digest is no longer served. Fix:
  re-resolve with `docker buildx imagetools inspect <image:tag>` and update the
  digest in `infra/docker-compose.yml`.

- **High idle CPU.** The collector and the health polling do steady background
  work. Fix: raise the `interval` on the healthchecks, or stop the stack when
  not in use.

## Bring down

```bash
docker compose -f infra/docker-compose.yml down      # keep data volumes
docker compose -f infra/docker-compose.yml down -v   # also wipe volumes
```
