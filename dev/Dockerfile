# One development image for both ends: the server (with Chromium for autobumps), a client (mpv, Tk,
# Qt with QtWebEngine) and the test tools. The repo is bind-mounted at /app (compose.dev.yml).
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 HOME=/tmp \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-tk python3-dev gcc linux-libc-dev \
        mpv ffmpeg pulseaudio-utils fonts-dejavu-core \
        libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
        libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2 libdbus-1-3 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt /tmp/req/requirements-dev.txt
COPY server/requirements.txt /tmp/req/server/requirements.txt
COPY client/requirements.txt client/requirements-web.txt /tmp/req/client/
RUN python3 -m venv /opt/venv \
    && pip install --no-cache-dir -r /tmp/req/requirements-dev.txt -r /tmp/req/client/requirements.txt \
       -r /tmp/req/client/requirements-web.txt \
    && playwright install --with-deps chromium && chmod -R a+rX /opt/ms-playwright \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
