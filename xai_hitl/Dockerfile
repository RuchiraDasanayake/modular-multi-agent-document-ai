FROM python:3.13-slim

LABEL maintainer="XAI-HITL Service"
LABEL description="Explainable AI engine + Human-in-the-Loop feedback"

WORKDIR /app

COPY xai_hitl/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy NER model for entity extraction (list questions)
RUN python -m spacy download en_core_web_sm

# Pre-download BART model for generative Q&A (encoder-decoder, natural language answers)
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from transformers import AutoModelForSeq2SeqLM, AutoTokenizer; AutoTokenizer.from_pretrained('vblagoje/bart_lfqa'); AutoModelForSeq2SeqLM.from_pretrained('vblagoje/bart_lfqa'); print('bart_lfqa cached')"
ENV TRANSFORMERS_OFFLINE=1

COPY xai_hitl/ ./xai_hitl/

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app/.cache
USER appuser

EXPOSE 8003

HEALTHCHECK --interval=10s --timeout=15s --start-period=240s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"

CMD ["uvicorn", "xai_hitl.main:app", "--host", "0.0.0.0", "--port", "8003"]
