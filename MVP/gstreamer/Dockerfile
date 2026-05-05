FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-gi \
    python3-gi-cairo \
    python3-requests \
    gir1.2-gstreamer-1.0 \
    gstreamer1.0-plugins-base \
    libpangocairo-1.0-0 \
    fonts-dejavu-core \
    fontconfig \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gstreamer1.0-rtsp \
    libgstrtspserver-1.0-0 \
    gir1.2-gst-rtsp-server-1.0 \
    librsvg2-common \
    && rm -rf /var/lib/apt/lists/*

COPY overlay_pipeline.py /app/

WORKDIR /app
ENTRYPOINT ["python3", "/app/overlay_pipeline.py"]
