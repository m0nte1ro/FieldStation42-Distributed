# Development image: the server's dependencies plus what the tests need.
# The repo is bind-mounted at /app, so nothing is copied in.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 HOME=/tmp

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libtk8.6 \
    && rm -rf /var/lib/apt/lists/*

COPY install/requirements-server.in /tmp/requirements-server.in
RUN pip install --no-cache-dir -r /tmp/requirements-server.in pytest httpx python-mpv-jsonipc

WORKDIR /app
