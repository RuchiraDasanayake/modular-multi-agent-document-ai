FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
COPY scripts/product_migrations/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY scripts/product_migrations/ ./product_migrations/
RUN useradd --create-home --shell /usr/sbin/nologin migrator
USER migrator

CMD ["alembic", "-c", "/app/product_migrations/alembic.ini", "upgrade", "head"]
