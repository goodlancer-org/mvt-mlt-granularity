# GEOMAPS Converter
# GDAL 3.13.3 + Python 3.14 + MLT binary wheel

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.3

ARG PMTILES_VERSION=1.31.2

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-venv \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python environment.
# --system-site-packages makes GDAL's matching osgeo bindings visible.
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN python -m pip install --upgrade pip

# PMTiles CLI
RUN ARCH="$(uname -m)" && \
    if [ "$ARCH" = "x86_64" ]; then GO_ARCH="x86_64"; \
    elif [ "$ARCH" = "aarch64" ]; then GO_ARCH="arm64"; \
    else echo "Unsupported arch: $ARCH" && exit 1; fi && \
    curl -fL -o /tmp/pmtiles.tar.gz \
    "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_${GO_ARCH}.tar.gz" && \
    tar -xzf /tmp/pmtiles.tar.gz -C /tmp && \
    mv /tmp/pmtiles /usr/local/bin/pmtiles && \
    chmod +x /usr/local/bin/pmtiles && \
    rm -f /tmp/pmtiles.tar.gz

WORKDIR /app

COPY requirements.lock .

# Important: fail instead of silently compiling packages from source.
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock

COPY config.yaml .
COPY src/ src/

ENTRYPOINT ["python", "-m"]
CMD ["src.convert", "--help"]
