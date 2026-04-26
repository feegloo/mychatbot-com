FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY chatrag_worker ./chatrag_worker

CMD ["python", "-m", "chatrag_worker.main"]
