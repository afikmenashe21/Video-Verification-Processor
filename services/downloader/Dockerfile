FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/downloader/pyproject.toml /app/services/downloader/
COPY services/downloader/downloader/ /app/services/downloader/downloader/
RUN pip install --no-cache-dir /app/services/downloader

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "downloader.main"]
