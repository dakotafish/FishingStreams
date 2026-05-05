FROM ubuntu:24.04

ARG MEDIAMTX_VERSION=v1.9.3
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tar \
    && rm -rf /var/lib/apt/lists/*

# MediaMTX release filenames use "arm64v8" for ARM, not "arm64".
# Map TARGETARCH to the correct release filename segment before downloading.
RUN set -eux; \
    ARCH="${TARGETARCH}"; \
    [ "$ARCH" = "arm64" ] && ARCH="arm64v8"; \
    curl -fsSL \
      "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/mediamtx_${MEDIAMTX_VERSION}_linux_${ARCH}.tar.gz" \
    | tar -xz -C /usr/local/bin mediamtx

EXPOSE 8890/udp 8888/tcp

ENTRYPOINT ["/usr/local/bin/mediamtx"]
CMD ["/mediamtx.yml"]
