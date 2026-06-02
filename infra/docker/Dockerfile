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

ENV KOSPI_DATA_SOURCE=sample \
    KOSPI_DATABASE_URL=sqlite:////data/kospi_flow.db \
    KOSPI_RAW_DATA_PATH=/data/raw \
    KOSPI_PROCESSED_DATA_PATH=/data/processed \
    PORT=8000

VOLUME ["/data"]
EXPOSE 8000

# Honor the platform-provided $PORT; bind all interfaces for container hosts.
CMD ["sh", "-c", "python -m kospi_flow.cli serve --host 0.0.0.0 --port ${PORT:-8000}"]
