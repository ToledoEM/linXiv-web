# Roadmap

**Planned and proposed direction.**

What is planned or waiting, in one place. Issues are closed once they have an answer, so this file is where the open work lives; each item links the issue or pull request it came from. Closed issues stay readable, and the people who proposed or prototyped something are credited in the [changelog](https://github.com/ToledoEM/linXiv-web/blob/main/CHANGELOG.md) when it ships.

## Plan

- **Integration with LinXiv project**: smooth api integration with desktop tool of linxiv api. Functionalities and features are not expected to be match 100% but api integration and coherent with the team plans of the solutions provided for the personas users of LinXiv.
- **Plugins features integration**: creation of modularization of features by downloadable plugins.
- **Contributor lookup**: contributors for plugins or other features are welcome.
- **Awesome Self-host**: wait for requirements of awesome selfhost requirement for submission to index.
- **On-brand 404 page**: custom 404 page in the linXiv-web style.
- **Multi-user testing**: improve multiuser administration for admin ([ticket](https://github.com/ToledoEM/linXiv-web/issues/100)).
    - **Open user registration**: no admin approval.
    - **Open user registration**: needs admin approval.
    - **Open user registration**: invitation link.
    - **Closed registration**: no new accounts.
- **Admin notification**: chat webhooks, ntfy, Gotify.
- **Browser extension**: integration with the linXiv Firefox/Chrome extension for server.
- **Stack deployment**: a multi-container setup for many users and heavy concurrency, alongside the current single image.
- **Special install docs**: one page for the full stack and one for bare metal, marked as possible but untested. They would cover requirements, cloning the repos and the Rust build.
- **Sharing between users**: users share PDFs, notes, tags, projects and reading lists with each other, with peer-to-peer sharing options in Settings.
- **Peer-to-peer connection test**: test the connection before peer-to-peer sharing is built.
- **Replace PDF on the paper page**: the paper page would offer to replace the PDF and make clear the old file goes.
- **BibTeX fields**: saving from Search or the Home feed, PDF import and upload, adding from a PDF link, and Zotero CSL records all store no BibTeX fields. Project BibTeX export uses the CLI rather than the stored fields, and there is no form to edit the fields by hand.
- **Metadata refresh**: an AI or filename save overwrites the recorded metadata source. Refresh needs a DOI or arXiv id and ignores a stored PMID.
- **Batch edit guard**: leaving a page during a batch edit with the browser Back button isn't blocked.
- **RSS feeds**: Save and Dismiss only work for arXiv entries.

## How to help

- Check [CONTRIBUTING.md](https://github.com/ToledoEM/linXiv-web/blob/main/CONTRIBUTING.md) file
- Create new issue (or a closed issue can be reopened) or open a draft pull request. For a larger feature, please say so before building it, so two people don't build the same thing.
