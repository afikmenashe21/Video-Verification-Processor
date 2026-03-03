FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/scorer/pyproject.toml /app/services/scorer/
COPY services/scorer/scorer/ /app/services/scorer/scorer/
RUN pip install --no-cache-dir /app/services/scorer

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "scorer.main"]
