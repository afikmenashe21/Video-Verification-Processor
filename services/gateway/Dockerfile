FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/gateway/pyproject.toml /app/services/gateway/
COPY services/gateway/gateway/ /app/services/gateway/gateway/
RUN pip install --no-cache-dir /app/services/gateway

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "gateway.main"]
