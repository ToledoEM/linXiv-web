# Compatibility and resources

## linXiv versions

| linXiv-web | linXiv CLI / MCP |
|---|---|
| 0.1.x | v0.7.0 |

The image builds `linxiv` and `linxiv-mcp` from upstream source at the `LINXIV_REF` build arg (default `v0.7.0`).

## Resource usage

Measured on a home server (Intel i7-7560U, 4 threads, 16 GB RAM) with a library of about 6,000 papers, 6,000 PDFs and 2,000 tags:

| | |
|---|---|
| Image size | 357 MB on disk (91 MB compressed) |
| Memory, idle | 155–185 MiB |
| Memory, peak | 302 MiB |
| CPU, idle | under 1% |
| Data dir (`papers.db`, logs, state) | 16 MB |
| PDFs | 12 GB (on a separate USB disk) |

No CPU or memory limits were set.

## Bare metal requirements

Not supported, but feasible without code changes. Docker is the tested path. Running directly on a host needs:

- `linxiv` and `linxiv-mcp` built from the [linXiv repo](https://github.com/linxiv-dev/linXiv) at `v0.7.0` (Rust toolchain, `cargo build --release -p linxiv-cli -p linxiv-mcp`), on `PATH` or set with `LINXIV_BIN` / `LINXIV_MCP_BIN`
- PDFium library from linXiv's `scripts/fetch_pdfium.sh`, with `LINXIV_PDFIUM_LIB` set to its path
- Python 3.11+ and `uv` for the server (`cd server && uv sync --frozen --no-dev`)
- Node.js and `npm` to build the web UI once (`cd web && npm ci && npm run build`), with `LINXIV_WEB_STATIC_DIR` set to `web/dist`
- Data and PDF directories, with `LINXIV_DATA_DIR` and `LINXIV_WEB_DATA_DIR` set to the same path, plus `LINXIV_WEB_PDF_DIR`
- `<data dir>/pdfs` linked to the PDF directory, as `entrypoint.sh` does in the container
- `LINXIV_WEB_HOST` set for network access (the default is `127.0.0.1`)
- A service manager (systemd, launchd) to run `python -m app` as a non-root user and restart it

## PDF folder on an SMB share

Not tested on SMB, but the design allows it. Only the data dir must stay on a local disk.

Key points:

- Ownership: the container runs as uid 1000 and CIFS ignores `chown`. Mount with `uid=1000,gid=1000,file_mode=0644,dir_mode=0755`.
- Mount the share on the host (`/etc/fstab` or systemd, with `_netdev,nofail`) and bind-mount it as `/pdfs`, rather than using Docker's CIFS volume driver.
- Start order: the server refuses to start when the PDF folder is missing, which stops writes into an empty mount point. Start the container after the mount, for example with `x-systemd.automount`.
- Share offline: if the NAS sleeps or the network drops, PDF reads, imports and downloads fail, and on a hard mount they can hang until `LINXIV_WEB_TIMEOUT_LONG` (120 s). Library data is not affected.
- Speed: opening PDFs, the full-text indexer and layout moves run at network speed. The rest of the app does not touch the PDF folder.
- File names: with the "by journal" layout, SMB may reject or change characters in journal names that a Linux filesystem accepts.
