FROM python:3.13-slim

LABEL maintainer="XAI-HITL Service"
LABEL description="Explainable AI engine + Human-in-the-Loop feedback"

WORKDIR /app

COPY xai_hitl/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download RoBERTa-SQuAD2 model at build time (better accuracy + unanswerable detection)
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from transformers import pipeline; pipeline('question-answering', model='deepset/roberta-base-squad2', handle_impossible_answer=True); print('roberta-base-squad2 cached')"
ENV TRANSFORMERS_OFFLINE=1

COPY xai_hitl/ ./xai_hitl/

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app/.cache
USER appuser

EXPOSE 8003

HEALTHCHECK --interval=10s --timeout=10s --start-period=180s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"

CMD ["uvicorn", "xai_hitl.main:app", "--host", "0.0.0.0", "--port", "8003"]
