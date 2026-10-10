# Security Policy

## Supported versions

linXiv-web is under active development. Security fixes go to the latest published image and the `main` branch only.

| Version | Supported |
| --- | --- |
| Latest image (`ghcr.io/toledoem/linxiv-web`) | Yes |
| `main` (unreleased) | Yes |
| Older images | No |

Vulnerabilities in the bundled `linxiv` CLI or `linxiv-mcp` belong upstream at [linxiv-dev/linXiv](https://github.com/linxiv-dev/linXiv). If you are unsure which side a problem is on, report it here and it will be forwarded.

## Reporting a vulnerability

Do **not** open a public issue, pull request or discussion.

Use GitHub private vulnerability reporting: the repository's **Security** tab → **Report a vulnerability**. Include:

- affected version (image tag or commit),
- how the instance is exposed (loopback, LAN, reverse proxy),
- steps to reproduce and the impact you observed.

Reports are acknowledged within 7 days. Disclosure is coordinated within 90 days of acknowledgement, on a date agreed with the reporter.

## Scope notes

linXiv-web is a single-user, self-hosted server. Most relevant: authentication and sessions, CSRF, file upload and archive handling, outbound requests (SSRF), the `/mcp` bridge and its token, and anything that reads or writes outside the data and PDF directories.
