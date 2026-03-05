FROM python:3.13-slim AS builder

WORKDIR /build
COPY gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim

LABEL maintainer="API Gateway"
LABEL description="Authentication + reverse proxy to AHMN / Guardrails / XAI-HITL"

WORKDIR /app

# Copy pre-built dependencies
COPY --from=builder /install /usr/local

COPY gateway/ ./gateway/

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
