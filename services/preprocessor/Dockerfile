FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libavformat-dev libavcodec-dev libavutil-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/preprocessor/pyproject.toml /app/services/preprocessor/
COPY services/preprocessor/preprocessor/ /app/services/preprocessor/preprocessor/
RUN pip install --no-cache-dir /app/services/preprocessor

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "preprocessor.main"]
