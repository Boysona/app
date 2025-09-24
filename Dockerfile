# Dockerfile (tusaale, Python app)
FROM python:3.11-slim

# ku dar deps lagama maarmaan ah, rakib ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
CMD ["python3 main.py ", "main:app", "--bind", "0.0.0.0:8080"]
