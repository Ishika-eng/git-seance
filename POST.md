---
title: Git Séance: raising a repo's deleted files and asking what still haunts it
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26)*

## What I Built

Every repository has a graveyard: the files someone deleted. `git log` knows who wrote each one, when it was born, when it died and what the commit message said at the funeral. Nobody ever reads it.

Git Séance digs it up. It finds a repo's deleted files and gives each a tombstone made only of git facts. A local open-weight model then lets the file speak, and you can question it. The part I like best is what it does beyond the voice:

- **Last rites.** The one I would actually keep installed. `git seance --install-hook` adds a pre-commit hook. When you stage a deletion, it tells you which living files still mention the one you are about to kill, before the broken delete lands. `--eulogy` lets the file say goodbye.
- **Successors.** For each dead file it finds what replaced it: a git rename, or the file added in the same commit whose lines overlap most, shown as a percentage.
- **Zombies.** Files that died and came back, and how many times.
- **Hauntings.** It searches the living code for lines that still mention a dead file, such as an import of a module that no longer exists. Deleted files are not always gone.
- **Reincarnations.** If a "deleted" file was only renamed (`useWebSocket.js` became `.jsx`), it says so instead of pretending it died.
- **The coroner's report.** Who deleted the most, the commit that was a mass grave, the average lifespan.
- **`--talk`.** A séance. Ask a deleted file why it died. It only knows its own code and history, and says "I do not remember" when you ask anything else.
- **`--raise`.** Restores the file's last living version into a folder. Your repo is untouched.
- **`--html`.** A self-contained graveyard page with moonlight, fog, clickable tombstones and a birth-to-death chart of every ghost. No network, no scripts.
- **A real git command.** `pip install git+https://github.com/Ishika-eng/git-seance` gives you `git seance`.

I took the theme two ways at once: the spooky one (a file speaking from beyond `git rm`, still haunting its old imports) and the Día de los Muertos one (honoring work that existed, mattered for a while, and was set down on purpose).

Here is the coroner's report and one tombstone from my own college project:

```
THE CORONER'S REPORT
13 souls lie here, living 17 days on average.
Longest life: app/frontend/src/pages/Demo.jsx (18 days).
Hands that deleted the most: Ishika (13)
Worst night: commit cb3fbaa3 took 9 files at once: "Central config and real sentence embeddings for ATMC"

╭─────────────────────────────────────╮
│             R . I . P .             │
│      pilot/run_poison_pilot.py      │
│       2026-09-22 - 2026-10-10       │
│       lived 18 days, 157 lines      │
│               "main()"              │
│  cause of death: collateral damage  │
╰─────────────────────────────────────╯
```

And a séance with that file, where the last answer is the one I was checking for:

```
you > why were you deleted?
run_poison_pilot.py > I was deleted because the project's goals shifted, and the team decided to
incorporate a self-evolving coding assistant loop, evaluation harness, and Assistant UI. [...]
you > what is the capital of France?
run_poison_pilot.py > I do not remember.
```

And the hook, in a real `git commit` in a small repo I made to test it:

```
$ git rm billing/invoice_formatter.py
$ git commit -m "Remove the old invoice formatter"
  LAST RITES: 1 file staged for deletion.

  billing/invoice_formatter.py  (7 lines, born 2025-03-01 by Ada, lived 607 days)
  Still haunting 2 places:
    README.md:2  Invoices are formatted by billing/invoice_formatter.py
    main.py:1  from billing.invoice_formatter import format_invoice
```

That `main.py` line is a broken import the commit would have shipped. The full transcript, with the file's eulogy, is in [`examples/last-rites.txt`](https://github.com/Ishika-eng/git-seance/blob/main/examples/last-rites.txt).

## Demo

Git Séance is a command line tool, so there is nothing deployed. This is the graveyard page it generated for my college project, with one tombstone opened:

![The graveyard page, one tombstone opened](https://raw.githubusercontent.com/Ishika-eng/git-seance/main/examples/graveyard.jpg)

The full run (graveyard page, ofrenda and raw terminal output) is in [`examples/`](https://github.com/Ishika-eng/git-seance/tree/main/examples). To try it on your own repo: `python3 seance.py /path/to/repo --html graveyard.html`.

<!-- TODO (optional): a short screen recording of the terminal run and `--talk` would make this stronger. -->

## Code

{% embed https://github.com/Ishika-eng/git-seance %}

## How I Built It

- **Git does the remembering.** `git log --diff-filter=D` lists deletions. `git show <commit>^:<path>` recovers the last version, and `git log --diff-filter=A --follow` finds the birth. Lifespan, line count, last words and the coroner's numbers are computed, never generated. `git grep` on HEAD finds the hauntings, and `git ls-files` spots the reincarnations.
- **An open-weight model does the speaking.** Qwen2.5-Coder 7B Instruct (Apache 2.0) runs through Ollama at `localhost:11434`. The tool streams tokens from it using Python's standard library, so the ghost speaks as the model writes. There are no dependencies to install.
- **The model is fenced in.** The system prompt says to use only the facts and code given, never invent names, dates or reasons, and to admit when it does not know. Facts and voice are always shown separately, so you can see which part is git and which part is the model.
- **Tested without a model.** Thirty-three unit tests build throwaway git repos and check the facts, hauntings, reincarnation, successors, zombies, the coroner, last rites (including a real `git commit` with the hook installed, and refusing to overwrite someone else's hook), `--raise` (including refusing paths that escape its folder), `--talk` with a mocked model, the lifespan chart, and HTML escaping.
- **The hook is polite.** It only warns unless you add `--strict`, and `--install-hook` refuses to overwrite a pre-commit hook it did not write.

Two things went wrong while building it, and fixing them made it better:
- My cause-of-death guesser labelled "Remove the legacy script" as a *refactor*, because `move` matches inside `Remove`. A unit test caught it. Keywords now match only at the start of a word.
- My first version of hauntings was noisy. Running it on my other repos, a deleted `server/Dockerfile` got blamed for every mention of the live root `Dockerfile`, and a rename from `.js` to `.jsx` looked like a broken import. Now the bare name only counts if it is distinctive and no living file shares it, and renames are reported as reincarnations. Both cases have tests.

Honest notes on quality: the model is a 7B. It often admits "the reason is not recorded", but in the séance above it invented a reason ("the project's goals shifted") from a commit message that did not say that. That is why the git facts sit above every whisper. The broken import in the hook demo above comes from a small repo I built to test it, not from one of my real projects. On my real repos, hauntings mostly taught me what to filter out (shared names, renames), and successors found real moves: `useWebSocket.js` replaced by `.jsx` at 100%, and result files moved into a subfolder. Successor percentages under about 60% are a loose "looks somewhat similar" and I show the percentage so you can judge.

## Why Does Open Innovation Matter?

The files people delete are often the ones they would least like to paste into a hosted API: abandoned experiments, old client code, things with a bad commit message. Because the model runs on my machine, a repository's entire history can be read, questioned and turned into a graveyard page without any of it going anywhere. The only network call is to localhost, the HTML page loads nothing, and it works with the Wi-Fi off.

It is also a setting, not a dependency: `--model` takes any model Ollama can run. I did not benchmark closed models against this, so I will not claim it beats them. For this job, private and free to run was what mattered, and an open-weight 7B was enough.

## My Agent Session

<!-- TODO (optional): save this session with DevRelay and embed it. -->

## The Spirit of It

<!-- TODO: add one honest sentence about the moment it landed for you. Only you know whether it did. -->

## Prize Categories

<!-- TODO: only list a partner category if you actually used its technology. This project uses none, so consider removing this section. -->
