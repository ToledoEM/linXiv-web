# Where the data lives

Every library is a folder inside `data/`. In single-user mode only the first row exists; [multi-user mode](index.md) adds the others.

| Path in `data/` | Contents |
|---|---|
| `papers.db`, `user_settings.json`, `pdfs/` | The owner's library, as before |
| `libraries/shared/` | The shared library: `papers.db`, `user_settings.json`, `pdfs/` |
| `libraries/u<id>/` | One account's library, same layout |
| `linxiv-web-state.db` | Accounts (password hashes only), sessions, the multi-user switch |

Libraries are created the first time they are opened. To keep the PDFs of the shared and per-account libraries on another disk, set `LINXIV_WEB_LIBRARIES_PDF_DIR`; each library then links its `pdfs/` to `<that folder>/<library>`. The folder must not be inside `LINXIV_WEB_PDF_DIR`.

**Settings → Server & data → Backup** backs up, imports and restores the library you are looking at. Copying the whole `data/` and `pdfs/` folders, as in [Backups](../self-hosting.md#backups), covers every library and every account.
