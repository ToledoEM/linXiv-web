# Browser add-on

The linXiv Firefox clipper is an unofficial Firefox add-on that saves what you're reading to your linXiv-web library. Click **Clip to linXiv** in the toolbar on any page, check the metadata it found, and save. There is no list of supported sites. A page with good metadata gives a full record, and a page with none still saves with its title and URL.

This page covers the add-on with linXiv-web. It can also save to the linXiv desktop app and `linxiv-headless`. The [add-on's own documentation](https://github.com/ToledoEM/linXiv-firefox-addon/tree/main/docs) covers those backends, how it works out metadata, and development.

## What gets saved

| You have open | What the add-on does |
|---|---|
| An article or any other web page | Saves metadata only. You attach the PDF yourself in linXiv-web |
| A page listing several papers | Offers a list to pick from, then saves the ones you tick |
| A PDF open full page | Sends the PDF to linXiv-web, which reads the metadata from the file |

## Install

The add-on isn't on addons.mozilla.org, so you build it from source and load it as a temporary add-on. Firefox removes a temporary add-on when it restarts, and you load it again the same way.

You need Firefox 140 or later, and Node 22 or later with pnpm 10 for the build.

```sh
git clone https://github.com/ToledoEM/linXiv-firefox-addon.git
cd linXiv-firefox-addon
pnpm install
pnpm build
```

Then load the build in Firefox:

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on**.
3. Pick `dist/manifest.json`.

## Connect it to linXiv-web

!!! warning "Needs a newer server"
    The add-on needs a linXiv-web newer than v0.1.3. An older server answers 404, and the add-on says it needs a newer version.

1. In linXiv-web, open Settings, then Integrations, and create a token on the [Browser add-on](guide/settings.md#browser-add-on) card. Each account has its own token, and it's shown only once. Creating a new one replaces the old one.
2. In the add-on, open the popup and click **Settings**.
3. Under **Save to**, choose linXiv-web.
4. Enter the server address, `http://127.0.0.1:8086` by default, and the token.
5. Click **Test connection** and accept the Firefox prompt. The add-on needs that permission to save, so run the test again whenever you change the address.

Settings save as you type and stay in this Firefox profile.

## Save a page

The add-on reads the current tab only when you click its button. The popup shows the type, title, authors, identifiers, journal, date and abstract it found. Check them, then click **Save to linXiv**.

If the page lists several items, such as search results or a reference list, the popup shows **Also on this page**, with a checkbox for each item and one for **This page**. Only **This page** starts ticked. Everything you tick is saved together.

The popup stays open and says whether the paper is new, already in your library, or had its PDF added. Saved papers go to the token owner's library and join the reading list **Imported - to check**, where [Check metadata](guide/projects.md) compares them with Crossref.

A save leaves a paper already in your library as it is. If that paper has no PDF yet, a PDF save adds one and keeps the metadata. Saving a paper that is in the trash restores it.

## Save a full-page PDF

Firefox doesn't let add-ons read its PDF viewer, so the popup shows only what the URL and tab title give. On save, the add-on requests the PDF again using your browser session and uploads the file, up to 100 MB. linXiv-web then reads the metadata from it. A PDF of a new paper is read twice on the server, so it takes about twice as long as an import in the web UI.

If the file turns out not to be a PDF, the add-on saves the tab as an ordinary page.

Allow and save
:   If Firefox blocks the request, the popup asks for your permission and shows **Allow and save**. Click it and accept the Firefox prompt, and the save carries on. A site that still can't be read, such as addons.mozilla.org, saves as an ordinary page.

Security checks
:   Some sites, such as ScienceDirect, answer the add-on's request with a security check page. The add-on opens the link in a new background tab and retries for about 15 seconds, and the tab closes by itself if the check passes. If the check needs you, solve it in the new tab, then press **Save to linXiv** there. Clicking in the new tab closes the popup, so you need that second press.

Expired links
:   `The PDF link answered HTTP 403`, or a similar status, means the link may have expired or need a login. Reload the PDF tab and try again. `The PDF link answered with a web page` means the same for a signed link.

## Errors

| Message | Meaning |
|---|---|
| `Can't reach <address>. Is the server running?` | Nothing answered at that address, or the request was blocked |
| `Firefox hasn't been given access to your server` | Run **Test connection** in Settings and accept the prompt |
| `Firefox needs permission to reach that address` | You declined the prompt. Run **Test connection** again |
| `linXiv-web rejected the token` | linXiv-web answered 401. Check the token |
| `This linXiv-web has no Browser add-on routes` | The server needs a newer version, or another service is on that address |
| `linXiv-web refused the addon: <reason>` | **Test connection** got a 403, for example because first-run setup isn't finished |
| `linXiv-web: <reason>` | A save failed, with the server's reason |
| `Saved, but ... didn't join the list` | The paper saved, but wasn't added to **Imported - to check** |
| `That address answered, but doesn't look like ...` | Another service is on that address, or you chose the wrong backend |

## What leaves your browser

| When | What | Where |
|---|---|---|
| The popup opens on a page with an identifier | That identifier | Crossref, DataCite, arXiv or NCBI E-utilities |
| You click **Save to linXiv** on a page | The BibTeX entries | Your server |
| You click **Save to linXiv** on a PDF tab | A request for the PDF, with your session cookies, then the file | The PDF's site, then your server |
| You run **Test connection** or save | Your token | Your server only |

The add-on removes the whole query string from a saved URL, so signed links aren't stored in a record. Requests to your server carry no cookies.

## Limitations

- The token is stored unencrypted in the Firefox profile.
- Permission for a server covers every port on that host, because Firefox match patterns can't name a port.
- Clicking outside the popup closes it, which likely ends a save in progress.
- The first save from a new PDF host shows **Allow and save**.
- A page with no date is stored with the date 1900-01-01.
- LibreWolf turns on HTTPS-only mode by default, including for local addresses, so a plain `http://` server may fail there. This case is untested.
- Zen and LibreWolf for macOS worked in manual testing. On Linux builds in Docker, both gave `NetworkError` on **Test connection** to a server at a private IP address. That test used `linxiv-headless`, and the cause is unknown.

The add-on's [limitations page](https://github.com/ToledoEM/linXiv-firefox-addon/blob/main/docs/limitations.md) has the full list, including results for PDFs imported into `linxiv-headless`.
