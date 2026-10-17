FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY apps/api apps/api
COPY pipelines pipelines
COPY services services
COPY db db
COPY tools tools
COPY alembic.ini ./
RUN useradd --create-home pulse && mkdir -p /app/.local/raw && chown -R pulse:pulse /app/.local
USER pulse
ENV PYTHONUNBUFFERED=1
EXPOSE 8020
CMD ["uv","run","--no-sync","uvicorn","apps.api.main:app","--host","0.0.0.0","--port","8020"]
