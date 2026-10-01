FROM ghcr.io/astral-sh/uv:0.11.24 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY ingestion ./ingestion

RUN useradd --create-home --uid 10001 ingestion
USER ingestion

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "-m", "ingestion.main"]
CMD ["--mode", "gcs"]
