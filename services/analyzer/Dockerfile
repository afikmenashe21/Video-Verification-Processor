FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/analyzer/pyproject.toml /app/services/analyzer/
COPY services/analyzer/analyzer/ /app/services/analyzer/analyzer/
RUN pip install --no-cache-dir /app/services/analyzer

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "analyzer.main"]
