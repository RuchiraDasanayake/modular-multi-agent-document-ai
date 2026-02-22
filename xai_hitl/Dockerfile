FROM python:3.13-slim

LABEL maintainer="XAI-HITL Service"
LABEL description="Explainable AI engine + Human-in-the-Loop feedback"

WORKDIR /app

COPY xai_hitl/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download DistilBERT model at build time
RUN python -c "from transformers import pipeline; pipeline('question-answering', model='distilbert/distilbert-base-cased-distilled-squad'); print('distilbert-base-cased-distilled-squad cached')"

COPY xai_hitl/ ./xai_hitl/

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8003/health', timeout=5)"

CMD ["uvicorn", "xai_hitl.main:app", "--host", "0.0.0.0", "--port", "8003"]
