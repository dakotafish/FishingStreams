FROM ubuntu:24.04

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
COPY configs /app/configs

ENV PYTHONUNBUFFERED=1

# Default config can be overridden at run time:
#   docker run ... pypeline --config configs/boat2.yaml
ENTRYPOINT ["python3", "/app/main.py"]
CMD ["--config", "/app/configs/boat1.yaml"]
