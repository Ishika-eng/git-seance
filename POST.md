---
title: Git Séance: the deleted files that still haunt your repo
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26)*

## What I Built

Every repository has a graveyard: the files someone deleted. `git log` knows who wrote each one, when it died, and what the commit message said at the funeral. Nobody reads it.

Git Séance does. It digs up a repo's deleted files, gives each a tombstone made only of git facts, and lets a local open-weight model speak for it. The spooky part turned out to be useful, because deleted files are not always gone. Something still points at them.

This is the feature I'd keep installed. `git seance --install-hook` adds a pre-commit hook. Stage a deletion and commit, and it checks what still mentions the file. This is a real `git commit` in a small repo I made to test it:

```
$ git rm billing/invoice_formatter.py
$ git commit -m "Remove the old invoice formatter"
  LAST RITES: 1 file staged for deletion.

  billing/invoice_formatter.py  (7 lines, born 2025-03-01 by Ada, lived 607 days)
  Still haunting 2 places:
    README.md:2  Invoices are formatted by billing/invoice_formatter.py
    main.py:1  from billing.invoice_formatter import format_invoice
```

That `main.py` line is a broken import the commit would have shipped. Add `--eulogy` and the file says goodbye in its own voice ([full transcript](https://github.com/Ishika-eng/git-seance/blob/main/examples/last-rites.txt)). The hook only warns unless you add `--strict`.

Run it over a repo's whole history and you get a graveyard:

- **Tombstones and a coroner's report**: who deleted the most, the commit that was a mass grave, the average lifespan, and the files that died and came back ("zombies").
- **Successors**: what replaced each dead file, as a git rename or the file added in the same commit that overlaps most, with the percentage shown.
- **Hauntings and reincarnations**: living code that still mentions a dead file, and files that were only renamed (`useWebSocket.js` became `.jsx`), which it reports as alive.
- **A séance** (`--talk`): ask a deleted file questions. It knows only its own code and history, and says "I do not remember" otherwise.
- **`--raise`** restores a file's last version into a folder, and **`--html`** writes a self-contained graveyard page.

I read the theme two ways at once: the spooky one (a file speaking from beyond `git rm`, still haunting its old imports) and the Día de los Muertos one (honoring work that existed, mattered for a while, and was set down on purpose).

Here is a tombstone from my own college project, and a séance with that file:

```
╭─────────────────────────────────────╮
│             R . I . P .             │
│      pilot/run_poison_pilot.py      │
│       2026-09-22 - 2026-10-10       │
│       lived 18 days, 157 lines      │
│               "main()"              │
│  cause of death: collateral damage  │
╰─────────────────────────────────────╯

you > why were you deleted?
run_poison_pilot.py > I was deleted because the project's goals shifted, and the team decided to
incorporate a self-evolving coding assistant loop, evaluation harness, and Assistant UI. [...]
you > what is the capital of France?
run_poison_pilot.py > I do not remember.
```

## Demo

Git Séance is a command line tool, so nothing is deployed. This is the graveyard page it generated for my college project, with one tombstone opened:

![The graveyard page, one tombstone opened](https://raw.githubusercontent.com/Ishika-eng/git-seance/main/examples/graveyard.jpg)

The full run is in [`examples/`](https://github.com/Ishika-eng/git-seance/tree/main/examples). Try it on your own repo:

```bash
pip install git+https://github.com/Ishika-eng/git-seance
git seance --html graveyard.html     # run inside any git repo
```

<!-- TODO (optional): a short screen recording of the hook and `--talk` would make this stronger. -->

## Code

{% embed https://github.com/Ishika-eng/git-seance %}

## How I Built It

- **Git does the remembering.** Deletions, births, lifespans, last lines and the coroner's numbers come from `git log`, `git show` and `git ls-files`. Hauntings come from `git grep`, and the hook searches the staged index with `git grep --cached`. None of it is generated.
- **An open-weight model does the speaking.** Qwen2.5-Coder 7B Instruct (Apache 2.0) runs through Ollama on localhost, streamed with Python's standard library. There are no dependencies to install.
- **The model is fenced in.** The prompt says to use only the facts and code given, never to invent names, dates or reasons, and to admit when it does not know. Facts and voice are always shown separately.
- **Tested without a model.** 33 unit tests build throwaway git repos. They include a real `git commit` with the hook installed, refusing to overwrite someone else's hook, and refusing `--raise` paths that escape their folder.

Two bugs made it better. My cause-of-death guesser labelled "Remove the legacy script" a *refactor*, because `move` matches inside `Remove`; a test caught it. And my first hauntings were noisy: running them on my other repos, a deleted `server/Dockerfile` was blamed for every mention of the live root `Dockerfile`, and a `.js` to `.jsx` rename looked like a broken import. Now a bare name only counts if it is distinctive and no living file shares it, and renames are reported as reincarnations.

**Where it falls short.** The model is a 7B. It often admits "the reason is not recorded", but in the séance above it invented a reason from a commit message that did not say that, which is why the git facts sit above every whisper. The broken import in the hook demo is from a repo I built to test it, not one of my real projects. On my real repos, hauntings mostly taught me what to filter out, while successors found real moves: `useWebSocket.js` replaced by `.jsx` at 100%, and result files moved into a subfolder. Successor matches under about 60% are loose guesses, so I show the percentage.

## Why Does Open Innovation Matter?

The files people delete are often the ones they would least like to paste into a hosted API: abandoned experiments, old client code, things with a bad commit message. Because the model runs on my machine, a repository's whole history can be read, questioned and turned into a graveyard page without any of it leaving. The only network call is to localhost, and the HTML page loads nothing from the network.

The model is also a setting, not a dependency: `--model` takes anything Ollama can run, and `--no-model` still gives you every git fact. I did not benchmark closed models, so I won't claim this beats them. For this job, private and free to run was what mattered, and an open-weight 7B was enough.

## My Agent Session

<!-- TODO (optional): save this session with DevRelay and embed it. -->

## The Spirit of It

<!-- TODO: add one honest sentence about the moment it landed for you. Only you know whether it did. -->
