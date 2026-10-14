# Contributing to linXiv-web

linXiv-web follows the same conventions as [linXiv](https://github.com/linxiv-dev/linXiv/blob/main/CONTRIBUTING.md), so the project can move into the linxiv-dev organization without churn.

## One-time setup

Turn on the repo's git hooks. They check commit messages:

```sh
git config core.hooksPath .githooks
```

All development runs in Docker; see [README.md](README.md#development).

## Branches

- **`main`** is where work lands. Branch from it and open your PR against it.
- **`release`** publishes. Only pull requests from `main` go into it (see [Releases](#releases)).
- **Name your branch `<type>/<short-slug>`**, using the same types as commit messages: `feat/`, `fix/`, `refactor/`, `perf/`, `docs/`, `test/`, `chore/`, `build/`, `ci/`, `style/`, `revert/`.
- Merged branches are deleted on GitHub 3 days after their pull request is merged (`branch-cleanup.yml`, daily).

## Releases

1. On a branch from `main`, set the new version in `server/pyproject.toml`, `server/app/main.py` (`__version__`) and `web/package.json` (plus `web/package-lock.json`), and give it a section in `CHANGELOG.md`. Merge to `main`.
2. Open a pull request from `main` into `release` and merge it.
3. `docker.yml` builds `ghcr.io/toledoem/linxiv-web:<version>` and `:latest` (amd64 + arm64), tags `v<version>` and creates a GitHub Release with the changelog section. It fails if the three versions differ or `v<version>` already exists.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): imperative summary`, at most 72 characters, no trailing period. A body is optional: one or two sentences of why, at most 5 lines and 150 characters. The full rules are in [`.githooks/commit-lint.sh`](.githooks/commit-lint.sh) (shared with linXiv).

## Pull requests

- Fill in the PR template, especially **Network calls** and **Debt or workarounds**.
- Keep PRs small and focused; split unrelated changes.
- CI checks every commit message, the server tests, and the frontend lint, type check and build. All must pass.

## License

linXiv-web is licensed under [Apache-2.0](LICENSE). By submitting a contribution you agree it is licensed under the same terms.
