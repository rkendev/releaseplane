# Runbook

How to bring up the ReleasePlane local dev stack and get green health checks
from a clean clone, plus the failure modes you are most likely to hit.

## Prerequisites

- Docker Engine and the Docker Compose plugin (`docker compose version`).
- For running tests and lint locally: `uv` (`uv sync` installs everything).

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
