# syntax=docker/dockerfile:1
#
# linXiv-web: FastAPI + React UI that drives the `linxiv` CLI as a subprocess.
#
# Stage 1 builds `linxiv` from upstream linxiv-dev/linXiv at LINXIV_REF. To
# build against a local checkout instead (submodules initialised):
#   docker build --build-arg LINXIV_SRC=local \
#     --build-context linxiv-local=../linXiv .

ARG LINXIV_REF=v0.7.1
ARG LINXIV_SRC=git

# --- linXiv source: pinned upstream tag (default) ---
FROM rust:1-bookworm@sha256:114c7a4425406451c2866b6aafe69fe29b1b298832db1277d411ac73c82d04d6 AS linxiv-src-git
ARG LINXIV_REF
RUN git clone --depth 1 --branch "${LINXIV_REF}" \
      --recurse-submodules --shallow-submodules \
      https://github.com/linxiv-dev/linXiv.git /src

# --- linXiv source: local checkout via --build-context linxiv-local=<path> ---
FROM scratch AS linxiv-src-local
COPY --from=linxiv-local scripts/ /src/scripts/
COPY --from=linxiv-local src-tauri/ /src/src-tauri/

FROM linxiv-src-${LINXIV_SRC} AS linxiv-src

# --- Stage 1: build the linxiv CLI and MCP server (Tauri-free crates, no webkit/gtk) ---
FROM rust:1-bookworm@sha256:114c7a4425406451c2866b6aafe69fe29b1b298832db1277d411ac73c82d04d6 AS cli-build
WORKDIR /src
COPY --from=linxiv-src /src/scripts/ scripts/
# Runtime dlopen'd PDF library (PDF import metadata extraction).
RUN bash scripts/fetch_pdfium.sh
COPY --from=linxiv-src /src/src-tauri/ src-tauri/
RUN rm -rf src-tauri/target src-tauri/vendor/pdfium/*.tgz
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/src/src-tauri/target,sharing=locked \
    cargo build --release --locked --manifest-path src-tauri/Cargo.toml \
      -p linxiv-cli --bin linxiv-cli -p linxiv-mcp --bin linxiv-mcp \
    && install -D src-tauri/target/release/linxiv-cli /out/linxiv \
    && install -D src-tauri/target/release/linxiv-mcp /out/linxiv-mcp \
    && install -D src-tauri/vendor/pdfium/lib/libpdfium.so /out/libpdfium.so

# Standalone CLI image, used for discovery and the real-CLI integration test.
FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8 AS cli
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=cli-build /out/linxiv /usr/local/bin/linxiv
COPY --from=cli-build /out/linxiv-mcp /usr/local/bin/linxiv-mcp
COPY --from=cli-build /out/libpdfium.so /usr/local/lib/pdfium/libpdfium.so
ENV LINXIV_PDFIUM_LIB=/usr/local/lib/pdfium/libpdfium.so \
    LINXIV_DATA_DIR=/data
ENTRYPOINT ["linxiv"]

# --- Server tests + lint, with the real CLI for the integration test ---
#   docker build --target server-test .
FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS server-test
COPY --from=ghcr.io/astral-sh/uv:0.8@sha256:1d31be550ff927957472b2a491dc3de1ea9b5c2d319a9cea5b6a48021e2990a6 /uv /usr/local/bin/uv
COPY --from=cli-build /out/linxiv /usr/local/bin/linxiv
COPY --from=cli-build /out/linxiv-mcp /usr/local/bin/linxiv-mcp
COPY --from=cli-build /out/libpdfium.so /usr/local/lib/pdfium/libpdfium.so
ENV LINXIV_PDFIUM_LIB=/usr/local/lib/pdfium/libpdfium.so \
    LINXIV_BIN=linxiv \
    LINXIV_MCP_BIN=linxiv-mcp
WORKDIR /app/server
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen
COPY server/ ./
RUN uv run ruff check . && uv run ruff format --check . && uv run pytest -rs

# --- Stage 2: build the React SPA ---
FROM node:25-slim@sha256:81db02c4b671288a03915da9534dbd54f96d0e7c24d80ccc54f5b36b2e684370 AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- Stage 3: Python runtime ---
FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8@sha256:1d31be550ff927957472b2a491dc3de1ea9b5c2d319a9cea5b6a48021e2990a6 /uv /usr/local/bin/uv

COPY --from=cli-build /out/linxiv /usr/local/bin/linxiv
# MCP server (stdio); the web server bridges it to /mcp when enabled in Settings.
COPY --from=cli-build /out/linxiv-mcp /usr/local/bin/linxiv-mcp
COPY --from=cli-build /out/libpdfium.so /usr/local/lib/pdfium/libpdfium.so
# linXiv version the CLI was built from, shown in Settings → About diagnostics.
ARG LINXIV_REF
ENV LINXIV_WEB_LINXIV_REF=${LINXIV_REF}

WORKDIR /app/server
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY server/app ./app
COPY --from=web-build /app/web/dist /app/web/dist
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN useradd -u 1000 -m appuser \
    && mkdir -p /data /pdfs \
    && chown appuser:appuser /data /pdfs \
    && chmod +x /usr/local/bin/entrypoint.sh

ENV PATH="/app/server/.venv/bin:${PATH}" \
    LINXIV_PDFIUM_LIB=/usr/local/lib/pdfium/libpdfium.so \
    LINXIV_DATA_DIR=/data \
    LINXIV_WEB_DATA_DIR=/data \
    LINXIV_WEB_PDF_DIR=/pdfs \
    LINXIV_WEB_STATIC_DIR=/app/web/dist \
    LINXIV_WEB_HOST=0.0.0.0 \
    LINXIV_WEB_PORT=8000

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('LINXIV_WEB_PORT', '8000'), timeout=4)"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "app"]
