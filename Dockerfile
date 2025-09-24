FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
EXPOSE 8080

CMD ["sh","-c","gunicorn main:app --bind 0.0.0.0:${PORT:-8080} --workers 2"]
