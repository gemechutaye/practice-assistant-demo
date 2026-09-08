FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.24 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services ./services
COPY supabase ./supabase
COPY infra/start.sh ./infra/start.sh
RUN groupadd --system assistant && useradd --system --gid assistant assistant \
    && chmod +x ./infra/start.sh \
    && chown -R assistant:assistant /app

USER assistant
EXPOSE 10000
ENTRYPOINT ["/app/infra/start.sh"]
CMD ["api"]
