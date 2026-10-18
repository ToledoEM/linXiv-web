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

## Raspberry Pi 5

It should run there, though nobody has tested it on a Pi yet. The image is published for `arm64`, the bundled `linxiv` CLI and PDF library have arm64 builds, and a peak of about 300 MiB fits on a 4 GB or 8 GB Pi 5. Three things to watch:

- Pull the prebuilt image. Building on the Pi compiles the Rust CLI, which is slow and needs plenty of RAM or swap.
- Keep the data dir on an SSD or NVMe drive, not the SD card, because SQLite writes to `papers.db` often.
- PDFs can sit on a USB or NVMe drive mounted at the PDF path.
