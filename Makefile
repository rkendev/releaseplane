# ReleasePlane developer tasks.
#
# `make check` lints and type-checks the package source and tests, then runs the
# test suite and prints a one-line test-count summary. Files outside the src and
# tests trees are still covered by `uv run pre-commit run --all-files`, which is
# the authoritative gate.

SRC := control-plane/src gateway/src evals/src sdk/src shared/src
TESTS := control-plane/tests gateway/tests evals/tests sdk/tests tests

# Host port the dev stack publishes Postgres on. The committed compose uses 5432;
# a local override may remap it (this is why `make migrate` takes PGPORT=5433).
PGPORT ?= 5432

.PHONY: check lint format typecheck test secrets lattice migrate \
        demo-config demo-up demo-admin demo-ports

# Compose invocation for the read-only demo. Every bring-up on a public-facing
# host must include the demo overlay, or the stack republishes on 0.0.0.0 and the
# exposure boundary is gone until someone notices. These targets exist so that is
# one word rather than a file list to remember.
DEMO_COMPOSE := docker compose -p releaseplane \
	-f infra/docker-compose.yml \
	-f infra/docker-compose.demo.yml

check: lint typecheck test

lint:
	uv run ruff check $(SRC) $(TESTS)
	uv run ruff format --check $(SRC) $(TESTS)

format:
	uv run ruff format $(SRC) $(TESTS)
	uv run ruff check --fix $(SRC) $(TESTS)

typecheck:
	uv run mypy $(SRC)

# Run the suite. Exit code 5 means pytest collected no tests, which is a valid
# state during early bootstrap; treat it as a zero-count pass.
test:
	@uv run pytest -q; ec=$$?; \
	if [ $$ec -eq 5 ]; then echo "test summary: 0 tests collected"; exit 0; fi; \
	exit $$ec

# Repo-level checks in the root tests/ tree: the Claude Code lattice wiring (ADR
# 0008) and the public-readiness guards (.gitignore secret coverage, the brand
# guard's behavior). Outside the package testpaths that `make check` runs, so
# it has its own target; CI runs it as the "Repo-level guards" step.
lattice:
	uv run pytest tests/ -q

# Write one secret file per value in .env (workspace root) into infra/secrets/.
# See infra/secrets.md. Never commit .env or the generated files. Files are
# world-readable (0644) because dev containers (e.g. grafana, uid 472) read them
# as non-root; production uses a separate 0400 path per infra/secrets.md.
secrets:
	@test -f .env || { echo "copy infra/.env.example to .env and fill it first"; exit 1; }
	@set -a; . ./.env; set +a; \
	printf '%s' "$$POSTGRES_PASSWORD"     > infra/secrets/postgres_password; \
	printf '%s' "$$MINIO_ROOT_PASSWORD"   > infra/secrets/minio_root_password; \
	printf '%s' "$$GRAFANA_ADMIN_PASSWORD" > infra/secrets/grafana_admin_password; \
	printf '%s' "$$CLAUDE_API_KEY"        > infra/secrets/claude_api_key; \
	printf '%s' "$$OPENAI_API_KEY"        > infra/secrets/openai_api_key; \
	chmod 0644 infra/secrets/postgres_password infra/secrets/minio_root_password \
	           infra/secrets/grafana_admin_password infra/secrets/claude_api_key \
	           infra/secrets/openai_api_key; \
	echo "wrote infra/secrets/{postgres_password,minio_root_password,grafana_admin_password,claude_api_key,openai_api_key}"

# Apply Alembic migrations to the running dev stack Postgres. Migrations do not
# run on container startup, so the persisted volume can lag head after the schema
# advances (a missing table shows up as a 500 from the matching endpoint). Run
# this after a bring-up. The container image does not ship the alembic/ tree, so
# run it from the host: the password comes from the secret file and the host port
# follows the published mapping (set PGPORT=5433 if a local override remaps it).
migrate:
	cd control-plane && \
	DATABASE_URL='postgresql+asyncpg://releaseplane@localhost:$(PGPORT)/releaseplane' \
	DATABASE_PASSWORD_FILE='$(CURDIR)/infra/secrets/postgres_password' \
	uv run alembic upgrade head

# Render the merged demo config without starting anything. Run this before a
# bring-up on a public host: it is where a missing overlay or an unset
# DEMO_ROOT_URL shows up.
demo-config:
	$(DEMO_COMPOSE) config

# Bring the stack up as the public read-only surface. See the "Read-only demo"
# section of docs/RUNBOOK.md.
demo-up:
	$(DEMO_COMPOSE) up -d

# Same stack with Grafana's login back on, for the owner over an SSH tunnel. The
# demo overlay stays in the file list, so the loopback binds hold; only the auth
# switches change. Anonymous access is off for the length of the session, so the
# public URL stops serving until `make demo-up` puts it back.
demo-admin:
	$(DEMO_COMPOSE) -f infra/docker-compose.admin.yml up -d

# The exposure check, on the host. Every line must read 127.0.0.1; none may read
# 0.0.0.0. This is necessary and not sufficient: the gate that counts is run from
# a client outside the host (docs/RUNBOOK.md).
demo-ports:
	@docker ps --filter "name=releaseplane-" --format '{{.Names}}\t{{.Ports}}'
