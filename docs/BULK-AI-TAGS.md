# Tagging every untagged paper with AI

Use this after a large import, when hundreds of papers have no tags and picking them one by one in the Library batch panel would take too long. `scripts/bulk-ai-tags.sh` runs on the machine that hosts the linXiv-web container. It asks the AI you set up in Settings → AI for tags for every paper that has none, and adds them.

Each paper gets the same suggestions as **AI Tags** on the paper page: the model reads the title, categories and abstract, and is steered toward tags your library already uses. The script adds all suggested tags, as the batch panel does when you approve without unticking any, or the first few with `--max-tags`.

The container keeps running and the web UI stays usable. The script talks to the server over `127.0.0.1`, so tags go through the server like any other edit.

## Requirements

- On the server: `sh`, `curl` and `jq` (`apt install jq` on Debian and Ubuntu).
- AI turned on in Settings → AI, with a provider, key and model saved, and **Test connection** passing. The script uses those saved settings; it has no provider options of its own.
- The container running with the compose file's port (`127.0.0.1:8086`), and the admin password set (first-run setup done, or `LINXIV_WEB_PASSWORD_HASH` in `.env`).

## Getting the script onto the server

Copy it next to your `docker-compose.yml`:

```sh
scp scripts/bulk-ai-tags.sh server:linxiv-web/
ssh server 'chmod +x linxiv-web/bulk-ai-tags.sh'
```

Then, on the server:

```sh
cd linxiv-web
./bulk-ai-tags.sh --help
```

See which papers it will pick up first. This makes no AI calls and changes nothing:

```sh
./bulk-ai-tags.sh --dry-run
```

## Running it

```sh
./bulk-ai-tags.sh
```

The script asks for the linXiv-web password and logs in. It checks the AI connection (the same check as **Test connection**) and stops there if AI is off or not set up. Then it reads the full list of untagged papers and works through it one paper at a time. Every paper gets one line in the output and in the log file:

```
started 2026-10-13 22:15:00: 858 untagged paper(s) on http://127.0.0.1:8086
AI gemini / gemini-2.5-flash, max tags per paper: all
OK    doi:10.1038/s41586-021-03819-2  2021/smith-rna.pdf  single-cell rna-seq, drug response, perturbation atlas (new)
NONE  local:9f3a0c1d  scans/notes.pdf  model returned no usable tags
SKIP  local:77c1e2b4  scans/blank.pdf  no title or abstract
FAIL  arXiv:2101.00001  -  (502): Gemini error 500: internal error
done: 812 tagged, 3 none, 41 skipped, 2 failed, 858 total. Log: ./bulk-ai-tags-20261013-221500.log
```

Each line shows the paper id, its PDF file inside the PDF folder (`-` when it has none) and the tags it got. `(new)` marks a tag that wasn't in your library before.

| Status | Meaning |
|---|---|
| `OK` | Tags added |
| `NONE` | The model answered, but every suggestion was empty, too long, or a duplicate. The paper stays untagged |
| `SKIP` | The paper has no title and no abstract, so it wasn't sent |
| `FAIL` | The AI call or the tag save failed. The message says why. When the save failed, the line lists the tags that weren't saved |

The exit status is 1 when any paper fails, and 0 otherwise. `NONE` and `SKIP` don't count as failures.

Options:

| Option | Effect |
|---|---|
| `--max-tags N` | Add only the first `N` suggestions per paper, 1 to 8. The default adds all of them (the model is asked for 3 to 6, the server keeps at most 8) |
| `--jobs N` | Ask the AI about `N` papers at a time, 1 to 4 (default 1). See [Running papers in parallel](#running-papers-in-parallel) |
| `--log FILE` | Log location (default `./bulk-ai-tags-<date>-<time>.log`) |
| `--dry-run` | List the untagged papers and how many would be skipped, then stop |

The script talks to the server at `http://127.0.0.1:8086`, the port `docker-compose.yml` publishes, so run it on the server itself. It also works when `LINXIV_WEB_COOKIE_SECURE=true`.

## Running papers in parallel

`--jobs 2` keeps two papers in flight: while the model answers one, the next request is already waiting. The server sends both to the provider at once; only its short library steps (reading the paper, saving the tags) take turns. Every paper still gets one line in the log, but the lines from the two workers mix, so they are no longer in list order.

```sh
./bulk-ai-tags.sh --jobs 2
```

It only helps when the AI end can work on two requests at the same time:

- **Cloud providers** (Gemini, OpenAI, Anthropic) answer parallel requests, but count each one against your rate limit. On a free tier, `--jobs 2` hits `429` twice as fast. Stay at 1 if the log fills with rate-limit failures.
- **LM Studio** answers parallel requests from version 0.4.0, on its llama.cpp engine (GGUF models, runtime llama.cpp v2.0.0 or later). Each loaded model has a **Max Concurrent Predictions** setting, which defaults to 4. To check or change it: open the model loader, turn on **Manually choose model load parameters**, pick the model, turn on **Show advanced settings**, and set **Max Concurrent Predictions** to at least the `--jobs` value. Then load the model again. Requests beyond that number wait in LM Studio's queue rather than failing. **Unified KV Cache** (on by default) lets the parallel requests share the context memory instead of splitting it into fixed parts.
- **Older LM Studio, or MLX models,** may handle one request at a time. The second request then waits for the first. The server gives each AI answer at most 300 seconds, and the wait counts toward that, so a slow model with `--jobs 2` can turn into `FAIL ... (502): ... request failed (ReadTimeout)` lines. Use `--jobs 1` there.

Parallel requests on a local model share the same GPU, so each answer comes back slower than alone. Total time still drops when the model runs well below the GPU's limits. Time the first lines of a run with `--jobs 1` and with `--jobs 2` and keep the faster one.

Tags that one worker adds don't reach a paper the other worker is tagging at the same moment, so two papers on a new topic can come back with two spellings of the same tag. Look through the `(new)` tags afterwards.

With more than one job, a lost login (the container restarted mid-run) isn't renewed. The affected papers are logged as `FAIL ... (401)`, and a rerun picks them up. Ctrl+C stops all workers. A paper whose tags were already on their way to the server still gets them.

## Running it again

A paper that got tags is no longer untagged, so a second run only picks up the `NONE`, `SKIP` and `FAIL` papers from the first one, plus anything imported since. Stopping a run with Ctrl+C is safe: the papers tagged so far keep their tags, and the next run carries on with the rest.

`SKIP` papers come back every run until they have a title or an abstract. Fix their metadata first (see below), or tag them by hand.

## Running it without a terminal (cron)

The script reads the password from the first line of the file named in `LINXIV_WEB_PASSWORD_FILE`. Keep that file readable only by you:

```sh
install -m 600 /dev/null ~/.linxiv-web-password
printf '%s\n' 'your-password' > ~/.linxiv-web-password
```

A crontab entry that tags whatever arrived during the day, after the nightly import from [BULK-IMPORT.md](BULK-IMPORT.md):

```
45 3 * * * cd $HOME/linxiv-web && LINXIV_WEB_PASSWORD_FILE=$HOME/.linxiv-web-password ./bulk-ai-tags.sh >> bulk-ai-tags-cron.log 2>&1
```

Five wrong passwords within five minutes lock out logins from that address for the rest of the five minutes (`429 too many login attempts`), so check the password file before you schedule it.

## What to expect

- **Time.** One AI call per paper, one at a time unless you pass `--jobs`. A cloud model takes a few seconds per paper. A local model in LM Studio or Ollama can take much longer, and the server waits up to 300 seconds for each answer from an OpenAI-compatible endpoint. Try `--dry-run` for the count, then time the first few lines.
- **Cost and rate limits.** With a cloud provider, every paper is one paid request. Free tiers often allow only a few requests per minute. When the provider answers with a rate-limit or overload error (429, 503 or 529), the script waits 30 seconds and tries that paper once more. If it fails again, the paper is logged as `FAIL` and picked up on the next run.
- **Vocabulary.** The prompt lists up to 400 of the library's existing tags, and the model is told to reuse them. Tags added earlier in a run count as existing for the papers after them, so a library with no tags yet builds its vocabulary as the run goes. Look through the `(new)` tags in the log afterwards. The Tags page lists every tag with its paper count, which makes near-duplicates easy to spot.
- **Thin records.** Papers imported from scans or PDFs without embedded metadata often have only a stray title and no abstract, and get poor tags. Fix those first: in the Library, tick papers marked `title?`, open batch edit, and look them up (with "By PDF file name" when the file names are titles). See [BULK-IMPORT.md](BULK-IMPORT.md#what-to-expect).
- **Removing tags.** The script only adds tags. To undo part of a run, remove the tags on the paper pages. The log lists every tag the script added, by paper.

Before tagging a large library, take a backup in Settings → Server & data → Backup.

## Troubleshooting

| Message | Fix |
|---|---|
| `jq not found` | Install jq on the server: `apt install jq` |
| `cannot reach http://127.0.0.1:8086` | The container is down, or the script isn't running on the server |
| `first-run setup is not done` | Open the web UI once and create the password |
| `login failed (401): invalid password` | Wrong password, or a stale `LINXIV_WEB_PASSWORD_FILE` |
| `login failed (429)` | Wait five minutes after repeated wrong passwords |
| `AI check failed (409): AI features are off` | Turn AI on in Settings → AI |
| `AI check failed (400): No … API key` | Add the provider's key in Settings → AI |
| `AI check failed (400): Choose a model` | Pick a model in Settings → AI and save |
| `AI check failed (400): Set the base URL …` | OpenAI-compatible provider: enter the endpoint's base URL in Settings → AI |
| `AI check failed (502): … request failed (ConnectError)` | The provider, or your local LM Studio or Ollama, can't be reached from the container |
| `FAIL … (502): … error 429` | The provider's rate limit, still hit after the retry. Run again later, or use a plan with a higher limit |
| `FAIL … (502): … did not return valid JSON` | The model ignored the reply format. Pick a stronger model, or run again: replies vary |
| `FAIL … (404)` | The paper was deleted while the run was going |
