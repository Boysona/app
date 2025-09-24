# Base image
FROM python:3.11-slim

# Environment
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FFMPEG_BINARY=/usr/bin/ffmpeg

# Install system deps (ffmpeg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# App dir
WORKDIR /app

# Install python deps (invalidate cache only when requirements change)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY . /app

EXPOSE 8080

# Start with gunicorn (ensure `gunicorn` is in requirements.txt)
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "120"]
