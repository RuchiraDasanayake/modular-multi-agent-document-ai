FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY idpo/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy IDPO module
COPY idpo/ ./idpo/
COPY configs/ ./configs/

# Create necessary directories and non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p inputs/inbox runs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')" || exit 1

CMD ["uvicorn", "idpo.ui.app:app", "--host", "0.0.0.0", "--port", "8004"]
