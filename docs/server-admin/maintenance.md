# Maintenance operations

Maintenance operations are jobs, for admins only, that check and tidy the libraries on the server. Three of them leave results for you to act on, each in its own section below: [duplicates](#duplicates), [papers left incomplete](#papers-left-incomplete) and [database backups on the server](#database-backups-on-the-server).

## Running operations

**Settings → Server Admin → Maintenance operations** lists jobs that look after every library on the server: the owner's, the shared one and each account's. Each row has a **Run** button, the result of its last run, and **Nightly** and **Monthly** boxes. Operations ticked Nightly run one after another once a night at the hour picked at the top of the card. Operations ticked Monthly run at that same hour once 30 days have passed since their last run finished (a Run by hand counts); an operation that never ran goes at the next nightly hour. The hour is the server's local time; set `TZ` on the container (for example `TZ=Europe/London`) when the server should not use UTC. A running operation shows its progress in the activity tray and can be cancelled.

## Operations

| Operation | What it does |
|---|---|
| Find duplicate papers | Reads every saved PDF and lists papers whose files are byte for byte the same on the **Duplicates** page. Only new or changed files are read again on later runs. |
| Complete metadata of new papers | For papers added since its last run that have one of the gaps ticked on its row (junk title, no authors, date, abstract, journal, DOI or BibTeX details), it looks the paper up by its own DOI or arXiv id, never by title, in the sources ticked on its row and in their order, and fills those empty fields. Stored values are kept. arXiv is asked only for arXiv papers, bioRxiv only for bioRxiv/medRxiv DOIs, Crossref and PubMed for any DOI. OpenAlex is not offered: linXiv can't look it up by an exact DOI. |
| Refresh metadata | Asks again the source each paper's metadata came from, by the paper's own id (DOI, arXiv id or OpenAlex work id), and replaces the stored title, authors, date, abstract, journal, DOI and BibTeX fields with the values it gets back. Empty values never replace stored ones, the link and tags stay, an arXiv subject code never replaces a journal, and a year-only date never replaces a full date of the same year. The source is recorded when a looked-up record is saved on the paper page or in batch edit, when a paper is added by DOI or arXiv id, and by "Complete metadata of new papers". Papers with no recorded source, or one that can't be asked again (BibTeX import, PDF file name, AI cleanup), are left alone. The option on its row picks **Papers published in the last year, and preprints** (arXiv, bioRxiv, medRxiv; the default) or **Every paper with a recorded source**. |
| Check PDF files | Reports papers whose PDF file is missing on disk, and PDF files in the PDF folder that no paper points at. It changes nothing. **Show report** lists them and breaks the folder down: files of any type, PDFs, each top-level subfolder, next to the number of papers, papers with a PDF, extra version files and PDFs of papers in the trash. **Skip folders** lists subfolders (for example `dup, errors`) that are counted but never reported as unlinked. **Download full list (TSV)** under each list has every missing paper or unlinked file, tab separated. **Move to orphans/** checks again and moves each unlinked PDF to `orphans/` under the same path; files changed in the last hour stay, and nothing is deleted. |
| Back up databases | Saves a copy of each library's database on the server and keeps the newest ones (7 unless you change it below the table). PDF files are not included. |
| Clean authors without papers | Deletes author records that no paper uses any more, for example the authors of papers deleted from the trash. linXiv refuses to delete an author still linked to a paper, so those are kept. It asks before running. |
| Clean tags without papers | Deletes tags that no paper and no project uses. Tags on papers in the trash stay, so a restored paper keeps its tags, and so do project tags such as `reading-list`. A tag named Untagged is always kept. It asks before running. |
| Empty trash | Deletes for good the papers that have been in the trash longer than the days typed on its row: 1 to 120, or 0 (the default) to never delete. Projects in the trash are left alone. It asks before running. |

The first run of "Complete metadata of new papers" looks at papers added in the last 30 days. Papers it completes also get the record's BibTeX fields that are still empty, and its source when none is recorded. "No BibTeX details" counts a paper with no BibTeX field stored at all; such a paper is complete once the source returns any BibTeX field, and its other values are left alone.

Refresh metadata pauses one second between lookups, as the sources are shared public services; on a large library, tick it Monthly rather than Nightly. Each library's papers that were not found are listed in `maintenance/metadata-refresh.json`.

## Duplicates

The **Duplicates** page (sidebar) shows the groups the last "Find duplicate papers" run found in the library you are looking at. Pick the paper to keep and click **Merge into kept paper**: linXiv moves the other papers' notes, highlights, projects, tags and PDFs to it, then deletes them. **Not duplicates** hides a group from later runs. **Download list (TSV)** saves every group, one row per paper, tab separated. The Library header links to the page while there are groups. In the shared library only admins can merge or dismiss.

## Papers left incomplete

Papers that "Complete metadata of new papers" could not finish are listed per library. The Library header shows **N to complete**; the link, or **Review papers left incomplete** in the operation's row, selects them and opens batch edit metadata. Saving fixes a paper and drops it from the list; **Skip** takes it off the list too.

## Database backups on the server

Below the operations, **Database backups on the server** lists the copies "Back up databases" made, per library, with **Download** and **Delete**. To restore one, download it, switch to that library and use **Restore** in Settings → Server & data → Backup. Backups and the other operation results live in `maintenance/` inside each library's data folder.
