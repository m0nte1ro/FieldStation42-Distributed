# The FieldStation42 server. Built from the repo root; server/Dockerfile.dockerignore keeps
# client/ out of the build context, so the image holds only server/ and shared/.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

# ffmpeg/ffprobe probe media durations, chapters and breaks when catalogs are built
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
# Chromium renders autobumps to video; it lives only in this image, never in the client's
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*

COPY shared shared
COPY server server
# upstream's default standby, static, sign-off and off-air media, copied into runtime/ on first start
COPY docs/static.mp4 docs/standby.png docs/brb.png docs/off_air_pattern.mp4 docs/signoff.mp4 /defaults/runtime/
COPY docs/logo_images /defaults/runtime/logo_images

EXPOSE 4242

ENTRYPOINT ["server/entrypoint.sh"]
CMD ["python3", "-m", "server.main"]
