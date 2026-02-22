FROM python:3.13-slim

LABEL maintainer="AHMN Backend"
LABEL description="FastAPI backend for Adaptive Hierarchical Memory Network"

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download ML models at build time so containers start fast
RUN python -c "\
    from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2'); \
    print('✓ all-MiniLM-L6-v2 cached')"

RUN python -c "\
    from transformers import pipeline; \
    pipeline('question-answering', model='distilbert/distilbert-base-cased-distilled-squad'); \
    print('✓ distilbert-base-cased-distilled-squad cached')"

RUN python -c "\
    from presidio_analyzer import AnalyzerEngine; \
    AnalyzerEngine(); \
    print('✓ Presidio NLP models cached')"

# Copy application code
COPY . .

# Component modules (ahmn_core, guardrails, xai_hitl) are mounted
# as read-only volumes via docker-compose.yml

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/health', timeout=5)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
