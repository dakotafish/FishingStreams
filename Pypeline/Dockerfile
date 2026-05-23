FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# System-level deps: Python + GStreamer plugin set + RTSP server bindings.
# Same base set as the MVP image, plus python3-pip so we can install
# pydantic/pyyaml from PyPI (the apt-shipped python3-pydantic is v1).
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gstreamer-1.0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gstreamer1.0-rtsp \
    libgstrtspserver-1.0-0 \
    gir1.2-gst-rtsp-server-1.0 \
    librsvg2-common \
    libpangocairo-1.0-0 \
    fonts-dejavu-core \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Browser overlay stack (Xvfb + Chromium + supervisord).
# The stock `chromium-browser` apt package on Ubuntu 24.04 is a transitional
# Snap stub that fails inside Docker; the xtradeb PPA ships a real .deb.
# The binary is named `chromium` (not `chromium-browser`) — supervisord.conf
# matches.
# Transparency in the overlay is handled by GStreamer's `alpha method=green`
# element chroma-keying the page's solid-green background, so no compositor
# (xcompmgr) is needed in the container.
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:xtradeb/apps \
    && apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    chromium \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Pure-Python deps. --break-system-packages because Ubuntu 24.04 ships PEP 668
# enabled; this is the container's only Python environment so a venv adds no
# value. Pin pydantic to v2 (the apt python3-pydantic package is v1).
RUN pip3 install --no-cache-dir --break-system-packages \
    'pydantic>=2,<3' \
    'pyyaml>=6,<7'

WORKDIR /app

# Copy the package, entrypoint, and configs. .dockerignore keeps venv,
# __pycache__, and reference/ out of the build context.
COPY pypeline /app/pypeline
COPY main.py /app/main.py
COPY overlay_server.py /app/overlay_server.py
COPY configs /app/configs
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

# supervisord now owns process startup. The Python pipeline command and
# config path are wired into supervisord.conf (program:gstreamer).
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
