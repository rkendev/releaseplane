FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Build context is the repo root (see infra/docker-compose.yml) so the neutral
# releaseplane-shared package is installed alongside the gateway: the runtime
# arithmetic policy imports it, and it is not on PyPI. Install shared first so it
# satisfies the gateway's dependency on it.
COPY shared ./shared
COPY gateway/pyproject.toml ./gateway/pyproject.toml
COPY gateway/src ./gateway/src
RUN pip install ./shared ./gateway

EXPOSE 8000
CMD ["uvicorn", "releaseplane_gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
