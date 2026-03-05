FROM python:3.13-slim

LABEL maintainer="AHMN Service"
LABEL description="Adaptive Hierarchical Memory Network microservice"

WORKDIR /app

# Install dependencies
COPY ahmn_core/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding model at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); print('all-MiniLM-L6-v2 cached')"

# Copy the AHMN core package
COPY ahmn_core/ ./ahmn_core/

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

CMD ["uvicorn", "ahmn_core.main:app", "--host", "0.0.0.0", "--port", "8001"]
