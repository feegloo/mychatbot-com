# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-cache-dir -r requirements.txt

COPY chatrag_worker ./chatrag_worker

RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

CMD ["python", "-m", "chatrag_worker.main"]
