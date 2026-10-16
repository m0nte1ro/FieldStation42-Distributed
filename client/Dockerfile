# A FieldStation42 client for a PC (a Pi runs the client natively: client/platform/install.sh).
# Built from the repo root; client/Dockerfile.dockerignore keeps server/ out of the build context,
# so the image holds only client/ and shared/. It draws on the host's X11 display and plays
# through the host's PulseAudio/PipeWire (see client/compose.yml).
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

# mpv plays, Tk draws the guide, Qt (PySide6 wheel) draws the OSD, overlays and web channels
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-tk python3-dev gcc linux-libc-dev \
        mpv pulseaudio-utils fonts-dejavu-core \
        libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
        libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2 libdbus-1-3 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

COPY client/requirements.txt /tmp/client-requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/client-requirements.txt \
    && apt-get purge -y gcc python3-dev && apt-get autoremove -y
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY shared shared
COPY client client
# upstream's default standby, static, sign-off and off-air media, copied into runtime/ on first start
COPY docs/static.mp4 docs/standby.png docs/brb.png docs/off_air_pattern.mp4 docs/signoff.mp4 /defaults/runtime/

ENTRYPOINT ["client/entrypoint.sh"]
CMD ["python3", "-m", "client.main"]
