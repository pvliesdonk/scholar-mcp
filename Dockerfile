FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Create non-root user early so COPY --chown works without recursive chown.
ARG APP_UID=1000
ARG APP_GID=1000
RUN if [ "$APP_UID" -eq 0 ] || [ "$APP_GID" -eq 0 ]; then \
        echo "ERROR: APP_UID and APP_GID must be non-zero" >&2; exit 1; \
    fi \
    && groupadd -r --gid $APP_GID --non-unique appuser \
    && useradd -r --uid $APP_UID --gid $APP_GID --no-log-init -d /app appuser \
    && mkdir -p /data/service /data/state/fastmcp \
    && chown appuser:appuser /data /data/service /data/state /data/state/fastmcp

WORKDIR /app

# Install dependencies first (cache layer).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev --extra all

# Copy source and install project.
COPY --chown=appuser:appuser . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra all \
    && chown -R appuser:appuser .venv

COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/
ENV PATH="/app/.venv/bin:$PATH" \
    FASTMCP_HOME=/data/state/fastmcp

EXPOSE 8000

VOLUME ["/data/service", "/data/state"]

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["scholar-mcp", "serve", "--transport", "http"]
