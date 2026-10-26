# Trash and backups

## Trash

Deleting a paper or project moves it to the Trash. Deleted papers stay there until you restore them or delete them forever, and a restored paper comes back with its PDF and project links. Deleted projects are listed below the papers and can be restored the same way.

Delete forever asks you to confirm and cannot be undone.

## Backups

**Settings → Server & data → Backup** has these actions:

- Download a backup: a snapshot of the database (papers, metadata, tags, projects, notes and authors). Saved PDF files are not included.
- Import: merges another linXiv database into this library.
- Restore: replaces the library with the backup. It is refused while a background job runs.
- Download settings / Import settings: every setting a Save can change, as a JSON file. API keys and tokens are left out of the file and stay as they are when you import one.

Admins can also keep backups on the server, made nightly or on demand: see [Database backups on the server](../server-admin.md#database-backups-on-the-server). The **Empty trash** maintenance operation deletes papers that have been in the trash longer than a set number of days (1 to 120).

Back up the PDF folder separately. [Self-hosting](../self-hosting.md#backups) shows which folders to copy.
