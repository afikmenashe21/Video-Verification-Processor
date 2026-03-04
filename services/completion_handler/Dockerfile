FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/completion_handler/pyproject.toml /app/services/completion_handler/
COPY services/completion_handler/completion_handler/ /app/services/completion_handler/completion_handler/
RUN pip install --no-cache-dir /app/services/completion_handler

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "completion_handler.main"]
