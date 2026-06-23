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

`.env.example` includes `OPENAI_API_KEY` as a placeholder (commented out) so the secret-loading path does not need to be retrofitted in Phase 5 when the second provider lands.
