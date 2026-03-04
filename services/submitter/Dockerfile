FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/submitter/pyproject.toml /app/services/submitter/
COPY services/submitter/submitter/ /app/services/submitter/submitter/
RUN pip install --no-cache-dir /app/services/submitter

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "submitter.main"]
