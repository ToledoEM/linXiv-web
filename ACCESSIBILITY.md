# Accessibility

linXiv-web should be usable by everyone, including people with disabilities and people who rely on assistive technology. If something in the app, the documentation, or the contribution process gets in your way, that is a bug, and it will be treated as one.

This project is maintained by one person in their spare time. That limits how fast things move, but it does not change how seriously accessibility reports are taken.

## Where things stand

linXiv-web has **not yet had a formal accessibility audit**, and it does not claim conformance with any standard. This statement describes what the project is aiming for, what is already known to be weak, and how to get a problem fixed.

## Goals

- **Target:** [WCAG 2.2](https://www.w3.org/TR/WCAG22/) Level AA, where feasible. This is a goal, not a conformance claim.
- **Keyboard:** every feature should be reachable and operable without a mouse, with a visible focus indicator and no keyboard traps.
- **Screen readers:** pages should use semantic HTML, labelled form controls, sensible heading order, and announce changes such as search results, errors, and background task status.
- **Vision and reading:** text and controls should meet AA colour contrast in both light and dark themes, colour should never be the only way information is conveyed, and the interface should stay usable at 200% browser zoom and at narrow widths.
- **Motion:** animations should respect the operating system's "reduce motion" setting.
- **Documentation:** the README and docs should use logical headings, descriptive link text, alt text for images, and real text instead of screenshots of text.

### What already helps

- Light and dark themes
- Zoom and density settings
- Keyboard shortcuts
- Knowledge graph data can be exported as GraphML or CSV, as a non-visual alternative to the graph view

## Known limitations

These areas are the most likely to cause problems. They are listed here so nobody has to discover them the hard way.

| Area | Limitation | Workaround |
| --- | --- | --- |
| Knowledge graph | The graph is a visual, pointer-driven view and is unlikely to work well with a screen reader or keyboard alone. | Export the graph as CSV or GraphML, or use the library table, author pages, and tag filters to reach the same papers. |
| PDF reader and highlights | Highlighting relies on text selection with a pointer. Many PDFs from arXiv and publishers are not tagged for assistive technology, which linXiv-web cannot fix. | Open the PDF in your preferred reader. For arXiv papers, the HTML version on arxiv.org is often more accessible when available. |
| Keyboard shortcuts | Shortcuts exist but are not fully documented, and they cannot yet be remapped or switched off. | Report any shortcut that clashes with your assistive technology. |
| Library table and batch editing | Sorting, selection, and batch actions have not been tested with screen readers. | None yet. Reports are welcome. |
| Third-party content | Abstracts, feeds, and metadata come from arXiv, OpenAlex, Crossref, PubMed, and bioRxiv/medRxiv and may contain unlabelled maths, images, or markup. | None within linXiv-web. |
| Firefox add-on | Not yet reviewed for accessibility. | Papers can be added from within the web UI instead. |

If you find a limitation that is not on this list, please report it so it can be added.

## Supported environments

linXiv-web is a web application. It is developed and tested against the latest versions of Firefox and Chromium-based browsers on desktop.

- **Safari and mobile browsers:** expected to work, but tested less often.
- **Screen readers:** the intent is to support NVDA with Firefox or Chrome, JAWS with Chrome, VoiceOver with Safari, and TalkBack with Chrome. None of these combinations has been systematically tested yet, so treat support as partial.

## Reporting an accessibility problem

Please [open an issue](https://github.com/ToledoEM/linXiv-web/issues/new) and put "Accessibility" in the title. You do not need to know which WCAG criterion applies or use any particular vocabulary. A plain description of what you were trying to do and what stopped you is enough.

If you can, include:

- What you were trying to do, and what happened instead
- The page or feature involved
- Your browser and operating system
- Any assistive technology you use, and its version (screen reader, magnifier, voice control, switch device, and so on)
- How badly it affects you (see severity below)

Reports from people with disabilities are treated as expert knowledge about how the app behaves in practice. You will not be asked to prove a problem is real or to justify why it matters.

### Severity

| Level | Meaning |
| --- | --- |
| Critical | A core task (signing in, searching, adding or reading a paper) is impossible. |
| Serious | A task is possible only with significant difficulty or a workaround. |
| Moderate | A task is harder or slower than it should be. |
| Minor | An annoyance or inconsistency that does not block anything. |

### What you can expect

- **Acknowledgement** within 7 days - I aim for less.
- **An honest answer** about what will happen next: a fix, a workaround, a request for more detail, or an explanation if something cannot be fixed soon and why.
- **Priority by impact.** Critical and serious problems are worked on ahead of new features. The aim is a fix or workaround within 30 days for critical issues and 60 days for serious ones. Moderate and minor issues are scheduled alongside other work.
- **Updates** on the issue if a target slips, so you are not left guessing.
- **A check with you** before the issue is closed, to confirm the fix works in your setup.

These are targets set by a single maintainer and may occasionally be missed. If they are, the issue will say so.

## For contributors

Changes that touch the user interface should keep accessibility intact. Before opening a pull request:

- **Keyboard:** tab through what you changed. Everything should be reachable, operable, and show visible focus.
- **Automated check:** run a tool such as [axe DevTools](https://www.deque.com/axe/devtools/) or Lighthouse on the affected pages and fix any new violations.
- **Semantics:** prefer native HTML elements (`button`, `a`, `label`, `table`) over custom ones. Use ARIA only when native HTML cannot express the behaviour.
- **Names and labels:** every control needs an accessible name. Icon-only buttons need a text label for assistive technology.
- **Images and icons:** meaningful images and SVGs need alt text or a title. Decorative ones should be hidden from assistive technology.
- **Colour:** check contrast in both themes, and do not rely on colour alone for state or meaning.
- **Motion:** respect `prefers-reduced-motion`.
- **Docs:** keep heading levels in order, write link text that makes sense out of context, and add alt text to screenshots.

Automated accessibility checks are not yet part of CI. Adding them is a welcome contribution. See [CONTRIBUTING.md](CONTRIBUTING.md) for general guidance.

If you are unsure whether a change is accessible, say so in the pull request. Asking is better than guessing.

## Ownership

Accessibility is owned by the project maintainer, [@ToledoEM](https://github.com/ToledoEM), who is responsible for triaging reports, tracking them to resolution, and keeping this document accurate.

## Feedback on this statement

If this statement is unclear, missing something, or wrong, please open an issue or a pull request. It will be updated as the app is tested and as problems are found and fixed.

_Last reviewed: November 2026_
