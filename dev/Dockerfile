# Development image: everything the tests need. The repo is bind-mounted at /app.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 HOME=/tmp

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt /tmp/requirements-dev.txt
COPY server/requirements.txt /tmp/server/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt

WORKDIR /app
