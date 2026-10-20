# A FieldStation42 client for a PC (a Pi runs the client natively: client/platform/install.sh).
# Built from the repo root; client/Dockerfile.dockerignore keeps server/ out of the build context,
# so the image holds only client/ and shared/. It draws on the host's X11 display and plays
# through the host's PulseAudio/PipeWire (see client/compose.yml).
# Trixie (glibc 2.41): PySide6-Essentials 6.8+ for arm64 needs glibc 2.39, more than bookworm has.
FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

# mpv plays, Tk draws the guide, Qt (PySide6 Essentials) draws the OSD and overlays
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-tk python3-dev gcc linux-libc-dev \
        mpv pulseaudio-utils fonts-dejavu-core \
        libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
        libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2 libdbus-1-3 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# no browser by default; --build-arg WEB_PAGES=true adds QtWebEngine for web channels and live autobumps
ARG WEB_PAGES=false
COPY client/requirements.txt client/requirements-web.txt /tmp/
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && if [ "$WEB_PAGES" = "true" ]; then \
         apt-get update && apt-get install -y --no-install-recommends libxkbfile1 && rm -rf /var/lib/apt/lists/* \
         && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements-web.txt; fi \
    && apt-get purge -y gcc python3-dev && apt-get autoremove -y
ENV PATH="/opt/venv/bin:$PATH"

# VA-API drivers let mpv decode on the GPU (AMD and Intel; a Raspberry Pi decodes through V4L2 instead)
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends mesa-va-drivers \
    && if [ "$TARGETARCH" = "amd64" ]; then apt-get install -y --no-install-recommends intel-media-va-driver i965-va-driver; fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY shared shared
COPY client client
# upstream's default standby, static, sign-off and off-air media, copied into runtime/ on first start
COPY docs/static.mp4 docs/standby.png docs/brb.png docs/off_air_pattern.mp4 docs/signoff.mp4 /defaults/runtime/

ENTRYPOINT ["client/entrypoint.sh"]
CMD ["python3", "-m", "client.main"]
