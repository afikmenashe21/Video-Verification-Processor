FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libavformat-dev libavcodec-dev libavutil-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app/ app/

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "app.main"]
