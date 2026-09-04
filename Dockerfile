FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py folder_service.py job_service.py serve.py ./
COPY templates ./templates
COPY static ./static
COPY models ./models

RUN mkdir -p /app/config /app/storage

EXPOSE 8080

VOLUME ["/app/storage", "/app/config"]

CMD ["python", "serve.py"]
