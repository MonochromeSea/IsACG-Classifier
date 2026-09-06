ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG REQUIREMENTS_FILE=requirements.txt
COPY requirements*.txt ./
RUN python3 -m pip install --no-cache-dir -r ${REQUIREMENTS_FILE} \
    && python3 -c "import watchdog; print('watchdog: ok')"

COPY app.py folder_service.py job_service.py serve.py ./
COPY templates ./templates
COPY static ./static
COPY models ./models

RUN mkdir -p /app/config /app/storage

EXPOSE 8080

VOLUME ["/app/storage", "/app/config"]

CMD ["python3", "serve.py"]
