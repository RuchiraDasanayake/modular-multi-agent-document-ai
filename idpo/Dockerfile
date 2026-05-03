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

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p inputs/inbox runs \
    && chown -R appuser:appuser /app

EXPOSE 8004

HEALTHCHECK --interval=10s --timeout=10s --start-period=30s --retries=8 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')" || exit 1

# Start as root to fix volume permissions, then drop to appuser
ENTRYPOINT ["sh", "-c", "chown -R appuser:appuser inputs runs 2>/dev/null; mkdir -p inputs/inbox runs; chown -R appuser:appuser inputs runs; exec su -s /bin/sh appuser -c 'uvicorn idpo.ui.app:app --host 0.0.0.0 --port 8004'"]
