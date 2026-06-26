# ReleasePlane developer tasks.
#
# `make check` lints and type-checks the package source and tests, then runs the
# test suite and prints a one-line test-count summary. Files outside the src and
# tests trees are still covered by `uv run pre-commit run --all-files`, which is
# the authoritative gate.

SRC := control-plane/src gateway/src evals/src sdk/src shared/src
TESTS := control-plane/tests gateway/tests evals/tests tests

.PHONY: check lint format typecheck test secrets lattice

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

# Presence/wiring checks for the Claude Code lattice (ADR 0008). Outside the
# default pytest collection (root tests/ is not in testpaths), so it has its own
# target rather than running on every `make check`.
lattice:
	uv run pytest tests/test_claude_lattice.py -q

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
