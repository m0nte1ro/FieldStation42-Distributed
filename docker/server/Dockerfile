FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

# ffmpeg/ffprobe for catalog builds; tk because a guide station makes the server import tkinter
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libtk8.6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY install/requirements-server.in install/requirements-server.in
RUN pip install --no-cache-dir -r install/requirements-server.in

COPY . .

EXPOSE 4242

CMD ["python3", "station_42.py", "--server"]
