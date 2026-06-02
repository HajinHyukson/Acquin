# Minimal image for the KOSPI Investor Flow API + jobs.
FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; add build-essential only if a wheel needs compiling.
COPY pyproject.toml README.md ./
COPY kospi_flow ./kospi_flow
COPY apps ./apps
COPY infra ./infra
COPY scripts ./scripts

# Install with the Postgres driver for production deployments.
RUN pip install --no-cache-dir -e ".[postgres]"

# Local fallback storage (used only if no KOSPI_DATABASE_URL / DATABASE_URL is
# set). Production uses managed Postgres, so no persistent volume is needed —
# Railway's builder rejects the Docker VOLUME instruction anyway.
ENV KOSPI_DATA_SOURCE=sample \
    KOSPI_RAW_DATA_PATH=/app/data/raw \
    KOSPI_PROCESSED_DATA_PATH=/app/data/processed \
    PORT=8000
RUN mkdir -p /app/data/raw /app/data/processed

EXPOSE 8000

# Honor the platform-provided $PORT; bind all interfaces for container hosts.
CMD ["sh", "-c", "python -m kospi_flow.cli serve --host 0.0.0.0 --port ${PORT:-8000}"]
