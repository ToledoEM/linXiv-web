# Browser add-on

The linXiv Firefox clipper is an unofficial Firefox add-on that saves the page you're reading to linXiv-web. Click **Clip to linXiv** in the toolbar, check the metadata, and save. Any site works: a page with good metadata gives a full record, one with none still saves its title and URL.

The add-on can also save to the linXiv desktop app and `linxiv-headless`. Those backends, metadata detection and development are covered in the [add-on's documentation](https://github.com/ToledoEM/linXiv-firefox-addon/tree/main/docs).

## What gets saved

| You have open | What the add-on does |
|---|---|
| An article or any other web page | Saves metadata only. Attach the PDF yourself in linXiv-web |
| A page listing several papers | Lets you pick from a list and saves the ones you tick |
| A PDF open full page | Sends the PDF. linXiv-web reads the metadata from the file |

## Install

The add-on isn't on addons.mozilla.org. Build it from source and load it as a temporary add-on, which Firefox removes on restart, so load it again after each restart. Requires Firefox 140+, Node 22+ and pnpm 10.

```sh
git clone https://github.com/ToledoEM/linXiv-firefox-addon.git
cd linXiv-firefox-addon
pnpm install
pnpm build
```

Load the build in Firefox:

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on**.
3. Pick `dist/manifest.json`.

## Connect it to linXiv-web

!!! warning "Needs a newer server"
    Requires linXiv-web v0.1.4 or newer. Older servers answer 404, and the add-on says it needs a newer version.

1. In linXiv-web, go to Settings > Integrations and create a token on the [Browser add-on](guide/settings.md#browser-add-on) card. One token per account, shown only once. A new token replaces the old one.
2. In the add-on popup, click **Settings** and set **Save to** to linXiv-web.
3. Enter the server address (default `http://127.0.0.1:8086`) and the token.
4. Click **Test connection** and accept the Firefox prompt. Saving needs that permission, so test again after changing the address.

Settings save as you type and stay in this Firefox profile.

## Save a page

The add-on reads the current tab only when you click its button. The popup shows the type, title, authors, identifiers, journal, date and abstract it found. Check them and click **Save to linXiv**.

On a page listing several items, such as search results or a reference list, **Also on this page** shows a checkbox per item plus one for **This page**, the only one ticked by default. Ticked items save together.

The popup stays open and reports whether the paper is new, already in your library, or had its PDF added. Saved papers go to the token owner's library and the reading list **Imported - to check**, where [Check metadata](guide/projects.md) compares them with Crossref.

Saving never changes a paper already in your library, except that a PDF save adds a PDF to a paper that has none, keeping its metadata. Saving a paper in the trash restores it.

## Save a full-page PDF

Firefox doesn't let add-ons read its PDF viewer, so the popup shows only what the URL and tab title give. On save, the add-on requests the PDF again with your browser session and uploads it (up to 100 MB), and linXiv-web reads the metadata from the file. The server reads a new paper's PDF twice, so this takes about twice as long as a web UI import. If the file isn't a PDF, the tab saves as an ordinary page.

Allow and save
:   If Firefox blocks the request, the popup shows **Allow and save**. Click it, accept the Firefox prompt, and the save continues. Sites that still can't be read, such as addons.mozilla.org, save as ordinary pages.

Security checks
:   Some sites, such as ScienceDirect, answer with a security check page. The add-on opens the link in a background tab and retries for about 15 seconds. The tab closes itself if the check passes. If the check needs you, solve it in that tab and press **Save to linXiv** there again, since clicking the tab closes the popup.

Expired links
:   `The PDF link answered HTTP 403`, or a similar status, means the link may have expired or need a login. `The PDF link answered with a web page` means the same for a signed link. Reload the PDF tab and retry.

## Errors

| Message | Meaning |
|---|---|
| `Can't reach <address>. Is the server running?` | Nothing answered at that address, or the request was blocked |
| `Firefox hasn't been given access to your server` | Run **Test connection** in Settings and accept the prompt |
| `Firefox needs permission to reach that address` | You declined the prompt. Run **Test connection** again |
| `linXiv-web rejected the token` | Server answered 401. Check the token |
| `This linXiv-web has no Browser add-on routes` | Server too old, or another service is on that address |
| `linXiv-web refused the addon: <reason>` | **Test connection** got a 403, for example first-run setup isn't finished |
| `linXiv-web: <reason>` | Save failed, with the server's reason |
| `Saved, but ... didn't join the list` | Paper saved but wasn't added to **Imported - to check** |
| `That address answered, but doesn't look like ...` | Another service is on that address, or wrong backend chosen |

## What leaves your browser

| When | What | Where |
|---|---|---|
| The popup opens on a page with an identifier | That identifier | Crossref, DataCite, arXiv or NCBI E-utilities |
| You click **Save to linXiv** on a page | The BibTeX entries | Your server |
| You click **Save to linXiv** on a PDF tab | A request for the PDF, with your session cookies, then the file | The PDF's site, then your server |
| You run **Test connection** or save | Your token | Your server only |

Saved URLs lose their whole query string, so signed links never reach a record. Requests to your server carry no cookies.

## Limitations

- The token is stored unencrypted in the Firefox profile.
- Server permission covers every port on the host, because Firefox match patterns can't name a port.
- Clicking outside the popup closes it, likely ending a save in progress.
- The first save from a new PDF host shows **Allow and save**.
- Pages with no date are stored as 1900-01-01.
- LibreWolf enables HTTPS-only mode by default, local addresses included, so a plain `http://` server may fail there (untested).
