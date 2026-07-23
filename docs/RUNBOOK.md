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
make demo-config                        # render first; a mistake shows up here
make demo-config | grep GF_SERVER_ROOT_URL   # must be the public origin
make demo-up
set -a; . infra/.env; set +a            # only if this host remaps ports
make migrate PGPORT=$${PG_HOST_PORT:-5432}
```

`infra/.env` is read by compose, not by the shell, so source it before passing
`PGPORT`. An unset `DEMO_ROOT_URL` falls back to `http://localhost:3000/`, which
sends Grafana's redirect and share links to the visitor's own machine, so check that
line before the first public bring-up.

`make demo-up` is the supported bring-up on a public-facing host, with `demo-build`
and `demo-down` for the rebuild and teardown. Prefer them to a hand-written compose
line every time: a bring-up, rebuild, or restart that forgets the overlay republishes
every service on `0.0.0.0`, and the guards in `tests/test_public_readiness.py` are
static checks that cannot catch that at runtime. The plain `docker compose` commands
elsewhere in this runbook and in the README are for a laptop or a private network.

The overlay is last in the `-f` order, so it decides the published ports. It carries
no host's port layout of its own: the numbers come from `PG_HOST_PORT`,
`CONTROL_PLANE_HOST_PORT`, `GATEWAY_HOST_PORT`, `MINIO_HOST_PORT`, and
`MINIO_CONSOLE_HOST_PORT`, defaulting to the base compose ports. A host that remaps
sets them in `infra/.env` (gitignored), which compose reads from the project
directory, and passes the matching `PGPORT=` to `make migrate`. `DEMO_ROOT_URL` sets
the public origin Grafana builds its redirect and share links from. See
`infra/.env.example`.


### What is exposed

| Surface | Public | Reached how |
| --- | --- | --- |
| Grafana (anonymous Viewer) | yes | proxy vhost to `127.0.0.1:3000` |
| Jaeger trace search | yes | proxy vhost to `127.0.0.1:16686` |
| control-plane API | no | loopback only |
| gateway `/invoke` | no | loopback only |
| Postgres, MinIO, Prometheus, OTel collector | no | loopback only |

Anonymous Viewer can read every provisioned dashboard and can issue read-only PromQL
through Grafana's datasource proxy. Postgres is not a Grafana datasource, so no
invoice data is reachable that way, and external snapshot sharing is off, so nothing
posts dashboard data outbound.

The Viewer role blocks the write endpoints that check a role, but Grafana counts an
anonymous visitor as signed in, so endpoints gated only on that were reachable. Five
are refused at the proxy instead (see the reverse-proxy section below and
`docs/SECURITY.md`). Read-only on this surface is the two together, Grafana's roles
and the vhost's refusals, not Grafana's roles alone.

The overlay also turns Grafana's authentication off, both the login form and basic
auth. The proxy forwards the whole service, so a login form on it is a public
credential oracle: Grafana's brute-force lockout bounds guessing one known account,
but nothing rate-limits by source. Nothing here needs runtime administration anyway,
since the dashboards and the datasource are provisioned from files.

**To administer Grafana**, layer the admin overlay on top rather than dropping the
demo one. Dropping it would republish every port on `0.0.0.0` for the length of the
session, which is a far larger hole than the login it reopens:

```bash
make demo-admin
ssh -N -L 3000:127.0.0.1:3001 <user>@<demo-host>
# then http://localhost:3000, admin / GRAFANA_ADMIN_PASSWORD from .env
make demo-up            # back to the public read-only surface
```

Note the `3001` on the remote side. Reopening the login is not enough on its own:
the vhost forwards `127.0.0.1:3000` whether or not an admin session is in progress,
so leaving Grafana there would put the login form, backed by the real admin password,
on the public hostname for the length of the session. The admin overlay moves Grafana
to `3001`, so the vhost's upstream is dead and the public URL answers 502 until
`make demo-up` puts it back. Which mode the instance is in follows from the port, not
from remembering to stop the proxy first.

The vhost forwards a port, not a container, so on a shared host confirm that nothing
else took `3000` while the demo was off it. Otherwise the public name serves whatever
did:

```bash
ss -ltnp 'sport = :3000'     # must be the releaseplane grafana, or nothing
```

`docs/SECURITY.md` has the full boundary and the probes that confirmed it.

Serving Grafana anonymously on the public internet means keeping it patched rather
than leaving the pin where it was set. Check the vendor advisories before a flip and
move the digest forward.

### Reverse proxy

The demo host fronts with Caddy, which issues and renews the certificates on its own,
so there is no certbot step. The vhosts live in `infra/caddy/releaseplane.Caddyfile`
as a fragment to append to the host's `/etc/caddy/Caddyfile`, with the real hostname
substituted for `<demo-host>` (the same one `DEMO_ROOT_URL` carries in `infra/.env`).

**Validate a candidate, then install it. Never append to the live file first.** That
file fronts every other site on the host, and a broken one persists: the reload
itself fails safe, leaving the previous config serving, but the bad text stays on
disk and takes everything down at the next restart or reboot, possibly days later.

```bash
cd /path/to/releaseplane        # the fragment path below is repo-relative
HOST=your.host.name             # no angle brackets; the real name
LIVE=/etc/caddy/Caddyfile

if grep -q "releaseplane demo (managed)" "$LIVE"; then
  echo "block already present; edit it in place rather than appending"
else
  # Alongside the live file, not in a shared /tmp: the merged content may carry a
  # neighbouring site's credentials, and any relative `import` or `{$ENV}` in the
  # host config resolves against the candidate's directory when Caddy adapts it.
  CAND=$(sudo mktemp "$LIVE.cand.XXXXXX")
  trap 'sudo rm -f "$CAND"' EXIT
  # Every step is chained. A candidate that is missing the live file's contents
  # is still valid Caddy, so an unguarded build step could install two site
  # blocks over the whole host config and drop every other site on it.
  sudo cp "$LIVE" "$CAND" \
    && { echo; sed "s/<demo-host>/$HOST/" infra/caddy/releaseplane.Caddyfile; } \
         | sudo tee -a "$CAND" > /dev/null \
    && sudo grep -q "releaseplane.$HOST" "$CAND" \
    && [ "$(sudo wc -c < "$CAND")" -gt "$(sudo wc -c < "$LIVE")" ] \
    && sudo caddy validate --config "$CAND" --adapter caddyfile \
    && sudo caddy reload --config "$CAND" --adapter caddyfile --force \
    && sudo cp -a "$LIVE" "$LIVE.bak.$(date +%F-%H%M)" \
    && sudo install -m "$(stat -c %a "$LIVE")" \
                    -o "$(stat -c %U "$LIVE")" -g "$(stat -c %G "$LIVE")" \
                    "$CAND" "$LIVE" \
    && echo "live and installed"
fi
```

Check the live file for a relative `import` or a `{$ENV}` reference before running
this. Both are resolved by the adapting process against the candidate's directory
and the invoking environment, which is why the candidate is built next to the live
file rather than somewhere else, and why a host that uses either deserves a look
before a reload rather than after.

Four things in that chain are there for a reason.

The two checks between the build and the validate are the ones that matter most. A
Caddyfile containing only these two site blocks parses perfectly, so `validate`
cannot tell a correct candidate from one where the `cp` failed and the fragment
landed alone. `grep` proves the substitution happened, which catches a wrong working
directory that would otherwise produce a candidate identical to the live file and
reload as a silent no-op; the size comparison proves the live content survived.

`reload` runs before `install`, not after. A config can adapt cleanly and still fail
to load, which is how the first version of these vhosts got as far as the live file
with a log path the running process could not open. Applying the candidate first
means only a config that actually loaded gets persisted, and a failure leaves both
the running server and the file on disk as they were.

`--adapter caddyfile` is needed on both commands because the candidate is not named
`Caddyfile`, and `reload` otherwise tries to parse it as JSON.

`install` reads the live file's current mode, owner, and group rather than forcing
`0644` and `root:root`. The merged file may carry a neighbouring site's credentials,
so this procedure has no business widening its permissions; and on a host where
Caddy owns its own config, changing the owner would leave it unable to read that
config at the next restart, taking every site down.

The `trap` removes the candidate on exit, since it holds the same merged content the
permissions above exist to protect. Note also what the reload-before-install ordering
does on a failure between the two: the running server has the new config while the
disk still has the old one. That divergence is the safe direction, a working site
that reverts on restart rather than a broken file that persists, but it does mean a
failure there needs finishing rather than ignoring.

The leading `echo` guards against a live file with no trailing newline, which would
otherwise glue the fragment onto the last existing line. The fragment's delimiter
comments make the block findable and removable later without disturbing the rest.
The double-append check is a fast, readable failure rather than a safety property:
under this procedure a duplicate would be caught by `validate` on the candidate and
could never reach the live file.

Watch it land:

```bash
sudo journalctl -u caddy --since "2 min ago" | grep -iE "error|certificate obtained"
```

Each vhost logs its requests to stderr, which systemd captures, so the access log is
`journalctl -u caddy | grep "handled request"`. Caddy redacts the Authorization
header on the way in.

Each block proxies a whole service rather than a path allowlist, which is why
Grafana's own authentication is switched off in the overlay: everything Grafana
serves is public. Five paths are the exception, refused at the proxy with a 405,
because Grafana treats an anonymous visitor as a signed-in user and every endpoint
gated on being signed in rather than on a role is therefore open: `/api/short-urls`
and its trailing-slash form (writes a row a `/goto/` link resolves), `/api/gnet/*`
(Grafana's proxy to grafana.com, which lets a visitor make the box originate
outbound requests), `/api/frontend-metrics`, and `/api/live/publish`. The fragment
records what each one returned before it was closed. Two hostnames rather than one
host with a `/traces` path, because Jaeger needs `QUERY_BASE_PATH` to serve its UI
under a subpath.

Confirm both names resolve before reloading. Wildcard-DNS names of the
`<label>.<ip-with-dashes>.sslip.io` form resolve without a record, but Caddy cannot
issue a certificate for a name that does not resolve to this host:

```bash
getent hosts "releaseplane.$HOST" "releaseplane-traces.$HOST"
```

After the reload, the first request to each name takes a few seconds while Caddy
obtains the certificate. Check that both did:

```bash
sudo journalctl -u caddy --since "2 min ago" | grep -i "certificate obtained"
```

To remove the block later, delete from the opening delimiter to the closing one and
run the same validate-then-install sequence.

### The reachability gate

The loopback bind is the control that holds, not the host firewall. Docker's DNAT
rules sit in the nat table ahead of the filter rules ufw manages, so unless the host
wires a `DOCKER-USER` rule, a published container port is reachable on the public IP
whatever ufw says about it. Confirm which way it renders:

```bash
make demo-ports
```

No line may contain `0.0.0.0`. Every published mapping must read `127.0.0.1:`;
entries with no host mapping at all (Jaeger exposes several inside the compose
network) are fine, since nothing on the host reaches them.

Take the port list from the merged config rather than from a fixed set of numbers,
so a host that remaps is covered without editing anything:

```bash
make demo-config | grep -E '^\s+published:' | grep -oE '[0-9]+' | sort -un
```

The config is the right source here, not `make demo-ports`. Two reasons: filtering
`ps` output on `127.0.0.1` would drop the one case this gate exists to catch, and
`ps` collapses adjacent ports into a range (`4317-4318->4317-4318`), so a naive
extraction silently loses one end of it. The config lists every published port
individually and states the intent the probe is checking.

Every one of those must fail from outside:

```
Test-NetConnection <public-ip> -Port <each-port-from-that-list>
```

Use a vantage that is not this host, since a `localhost` probe passes either way: a
laptop, not an SSH session into the box. Anything that resolves the public IP from
elsewhere works, and a second one is worth having. A closed port returns a connection
error and an open one returns something else; the distinction that matters is refused
versus answered rather than what the answer said.

Attribute an answering port before treating it as a failure. On a shared host,
another project's container may hold one of these numbers, which is a finding about
that project rather than about this stack. `docker ps --filter "publish=<port>"`
says whose it is.

If any raw port answers and belongs to this stack, the demo does not go live until it
is closed. The two demo names are the only things that may answer.

Then confirm both surfaces that are supposed to answer, and that the boundary holds
through the proxy rather than only on loopback. Run this from the repo root, and set
`HOST` again if this is a fresh shell:

```bash
G="https://releaseplane.$HOST"
J="https://releaseplane-traces.$HOST"

curl -s -o /dev/null -w 'grafana  %{http_code}\n' "$G/api/search"      # 200 anonymous
curl -s -o /dev/null -w 'jaeger   %{http_code}\n' "$J/"                # 200
curl -s -o /dev/null -w 'panels   %{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d '{"queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"up","instant":true}],"from":"now-5m","to":"now"}' \
  "$G/api/ds/query"                                                    # 200

# Grafana refuses these by role.
for p in /api/dashboards/db /api/annotations /api/datasources /api/snapshots; do
  curl -s -o /dev/null -w "role   $p %{http_code}\n" -X POST \
    -H 'Content-Type: application/json' -d '{}' "$G$p"                 # 401 or 403
done

# The vhost refuses these, because Grafana does not. A 405 is the proxy answering;
# anything else means the refusal did not load on this host, whatever the tracked
# fragment says.
for p in /api/short-urls /api/short-urls/ /api/gnet/plugins /api/frontend-metrics /api/live/publish; do
  curl -s -o /dev/null -w "vhost  $p %{http_code}\n" -X POST \
    -H 'Content-Type: application/json' -d '{}' "$G$p"                 # all 405
done

curl -s -o /dev/null -w 'login    %{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d '{"user":"admin","password":"x"}' "$G/login"                      # 400, no form

# The real password goes in on stdin, not the command line, so it stays out of the
# process list and the shell history on a host other people use.
printf 'user = "admin:%s"\n' "$(cat infra/secrets/grafana_admin_password)" \
  | curl -s -o /dev/null -w 'basic    %{http_code}\n' -K - "$G/api/user"  # 401
```

A 200 on the first three and a 4xx on the rest is the whole public contract. Three
lines carry most of the weight. The `basic` line proves the real password buys
nothing through the public URL, so there is no credential worth guessing there. The
`vhost` block must show 405 specifically: those paths are open in Grafana, so any
other code means the proxy refusal is not in force and the surface is writable. And
the `panels` line proves the dashboards still render, since it is the one POST the
surface has to allow, so a future method allowlist or filtering proxy that breaks the
demo shows up here rather than in a visitor's blank screen.

### Putting real data behind the dashboards (spends)

`infra/scripts/populate_demo.sh` is the one deliberate live-spend path outside the
eval baseline runs. Nothing invokes it automatically: CI never runs it, nothing
imports it, and it refuses to start without `RELEASEPLANE_DEMO_SPEND=i-accept` in
the environment. Estimated spend is **roughly $0.60 to $1.80** of the owner's own
credit, printed before anything runs, and the same again on a re-run.

It produces exactly what the dashboards need: a v1 release the gate blocks (the
discount-as-negative-line failure), a v2 release that passes and is promoted to
active, and three `/invoke` calls, one on the Sonnet default, one routed to
gpt-4o-mini, and one carrying a bad total so a policy event renders.

**Rehearse it first. The dry run is free and it has already caught a real bug:**

```bash
infra/scripts/populate_demo.sh --dry-run
```

That does everything costing nothing (preconditions, seeding, the gpt-4o-mini model
config and its routing rule, the dataset load, and creating the v1 release) and
stops before the first eval. It runs against the dummy-pinned stack, which is the
normal state, so there is no reason not to run it.

Then the real one:

```bash
# 1. Unpin the gateway so selection follows the model config.
#    Set GATEWAY_PROVIDER: "" in infra/docker-compose.override.yml, then:
make demo-up

# 2. Both provider keys must be present, or the run half-works.
make secrets     # from a .env carrying CLAUDE_API_KEY and OPENAI_API_KEY

# 3. Spend.
RELEASEPLANE_DEMO_SPEND=i-accept infra/scripts/populate_demo.sh

# 4. Re-pin to dummy and bring the stack back, before walking away from a stack
#    that can spend. Set GATEWAY_PROVIDER: "dummy" again, then:
make demo-up
docker inspect releaseplane-gateway \
  --format '{{range .Config.Env}}{{println .}}{{end}}' | grep GATEWAY_PROVIDER
```

The script refuses to run while the gateway is still pinned to `dummy`, because
that would score every case at zero, spend nothing, and look like it worked. It does
not edit the override file for you: on a shared host that file is local state a
script has no business rewriting, so step 4 is yours.

Two routing details are easy to get wrong and both cost a real invoke to notice.
Routing rules are keyed on the prompt's `use_case` (`ap_invoice_extraction`), not on
the prompt name, so a rule written against the name never fires; the script reads
the value from the prompt rather than carrying a literal. And a pinned `release_id`
never routes, by design, so the cost-tier invoke resolves by `prompt_name` against
the active release instead.

Afterwards, check the three surfaces:

| Surface | What should be there |
| --- | --- |
| eval dashboard | the v1 series under the 100% line on Tier-2, v2 on it |
| gateway dashboard | routing decisions split across both providers, one policy event |
| Jaeger | three traces carrying release_id, provider, cost, and policy status |

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
