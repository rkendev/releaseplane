# Secrets handling

## Layout

Secrets are file-mounted into containers via Docker Compose's `secrets:` block. They are never set as environment variables in `docker-compose.yml` and never committed.

```
infra/
  secrets/
    .gitkeep
    postgres_password        # local dev only; not committed
    minio_root_password      # local dev only; not committed
    grafana_admin_password   # local dev only; not committed
    claude_api_key           # local dev only; not committed
    openai_api_key           # local dev only; not committed (empty = OpenAI adapter skipped)
```

The `infra/secrets/` directory is committed empty (just `.gitkeep`). Every file inside it is in `.gitignore`.

## Load order

For local dev:

1. Developer copies `.env.example` to `.env` (workspace root). `.env` is gitignored.
2. Developer runs `make secrets` (Phase 1) which reads `.env` and writes one file per secret into `infra/secrets/`.
3. `docker compose up` mounts the files into the relevant containers at `/run/secrets/<name>`.
4. Application code reads the file path from `<NAME>_FILE` environment variables, not the value directly.

For prod (VPS):

1. Secrets live in `/etc/releaseplane/secrets/` on the VPS, mode `0400`, owned by the deploy user.
2. The Compose project on the VPS mounts that directory, not the in-repo one.
3. No secret value ever appears in the repo, the env file, or a container env block.

## Never-commit rule

`.gitignore` covers:

```
.env
infra/secrets/*
!infra/secrets/.gitkeep
```

CI runs `detect-private-key` via pre-commit on every PR.

## Multi-provider readiness

The second provider (OpenAI) landed in Phase 5. `.env.example` carries `OPENAI_API_KEY` (empty by default); `make secrets` writes `infra/secrets/openai_api_key` from it, and the gateway mounts it at `/run/secrets/openai_api_key` (read via `OPENAI_API_KEY_FILE`). An empty value is the clean skip: the gateway registry omits the OpenAI adapter and the stack runs on Dummy/Claude with zero OpenAI spend.
