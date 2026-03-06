FROM python:3.13-slim

LABEL maintainer="Guardrails Service"
LABEL description="5-layer hallucination detection & validation ensemble"

WORKDIR /app

COPY guardrails/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download ML models at build time into shared cache
ENV HF_HOME=/app/.cache/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface/sentence_transformers
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); print('all-MiniLM-L6-v2 cached')"
RUN python -c "from presidio_analyzer import AnalyzerEngine; AnalyzerEngine(); print('Presidio NLP models cached')"
ENV TRANSFORMERS_OFFLINE=1

COPY guardrails/ ./guardrails/

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app/.cache
USER appuser

EXPOSE 8002

HEALTHCHECK --interval=10s --timeout=10s --start-period=120s --retries=8 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"

CMD ["uvicorn", "guardrails.main:app", "--host", "0.0.0.0", "--port", "8002"]
