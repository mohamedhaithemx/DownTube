FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir --upgrade yt-dlp

COPY app/ ./app/
COPY frontend/ ./frontend/

RUN mkdir -p /tmp/downtube

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s \
  CMD curl -f http://localhost:8000/health || exit 1

ENV PORT=8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
