# GEOMAPS Converter
# GDAL 3.13.3 + Python 3.14 + MLT binary wheel

FROM rust:1.98.1-slim AS rust-toolchain

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.3 AS mlt-builder
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-venv build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup
ENV PATH="/usr/local/cargo/bin:/opt/build-venv/bin:${PATH}"
RUN python3 -m venv /opt/build-venv
COPY build_mlt.py /build/build_mlt.py
RUN python /build/build_mlt.py --work-dir /build/source --wheel-dir /wheels
COPY build_mlt_cli.py /build/build_mlt_cli.py
COPY rust /build/rust
RUN python /build/build_mlt_cli.py --source-dir /build/source/maplibre_tiles-0.4.1 --output-dir /mlt-bin

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
COPY --from=mlt-builder /mlt-bin /opt/mlt-bin
ENV MLT_RUST_CLI=/opt/mlt-bin/mlt-experiment

COPY requirements.lock .

# Install the source-verified binding before resolving runtime dependencies.
# Its 0.4.1 pin is then satisfied without requiring an upstream platform wheel.
COPY --from=mlt-builder /wheels /tmp/mlt-wheels
RUN pip install --no-cache-dir --no-deps /tmp/mlt-wheels/*.whl \
    && pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock \
    && rm -rf /tmp/mlt-wheels

COPY config.yaml .
COPY src/ src/

ENTRYPOINT ["python", "-m"]
CMD ["src.convert", "--help"]
