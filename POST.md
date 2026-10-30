---
title: Git Séance: raising a repo's deleted files and asking what still haunts it
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26)*

## What I Built

Every repository has a graveyard: the files someone deleted. `git log` knows who wrote each one, when it was born, when it died and what the commit message said at the funeral. Nobody ever reads it.

Git Séance digs it up. It finds a repo's deleted files and gives each a tombstone made only of git facts. A local open-weight model then lets the file speak, and you can question it. The part I like best is what it does beyond the voice:

- **Hauntings.** It searches the living code for lines that still mention a dead file, such as an import of a module that no longer exists. Deleted files are not always gone.
- **Reincarnations.** If a "deleted" file was only renamed (`useWebSocket.js` became `.jsx`), it says so instead of pretending it died.
- **The coroner's report.** Who deleted the most, the commit that was a mass grave, the average lifespan.
- **`--talk`.** A séance. Ask a deleted file why it died. It only knows its own code and history, and says "I do not remember" when you ask anything else.
- **`--raise`.** Restores the file's last living version into a folder. Your repo is untouched.
- **`--html`.** A self-contained graveyard page with moonlight, fog and clickable tombstones. No network, no scripts.

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

## Demo

<!-- TODO: add a short screen recording of `python3 seance.py <repo> --html graveyard.html`, then `--talk`, plus a screenshot of the graveyard page. Nothing is deployed; it is a command line tool. -->

## Code

{% embed https://github.com/Ishika-eng/git-seance %}

## How I Built It

- **Git does the remembering.** `git log --diff-filter=D` lists deletions. `git show <commit>^:<path>` recovers the last version, and `git log --diff-filter=A --follow` finds the birth. Lifespan, line count, last words and the coroner's numbers are computed, never generated. `git grep` on HEAD finds the hauntings, and `git ls-files` spots the reincarnations.
- **An open-weight model does the speaking.** Qwen2.5-Coder 7B Instruct (Apache 2.0) runs through Ollama at `localhost:11434`. The tool streams tokens from it using Python's standard library, so the ghost speaks as the model writes. There are no dependencies to install.
- **The model is fenced in.** The system prompt says to use only the facts and code given, never invent names, dates or reasons, and to admit when it does not know. Facts and voice are always shown separately, so you can see which part is git and which part is the model.
- **Tested without a model.** Twenty unit tests build throwaway git repos and check the facts, hauntings, reincarnation, the coroner, `--raise` (including refusing paths that escape its folder), `--talk` with a mocked model, and HTML escaping.

Two things went wrong while building it, and fixing them made it better:
- My cause-of-death guesser labelled "Remove the legacy script" as a *refactor*, because `move` matches inside `Remove`. A unit test caught it. Keywords now match only at the start of a word.
- My first version of hauntings was noisy. Running it on my other repos, a deleted `server/Dockerfile` got blamed for every mention of the live root `Dockerfile`, and a rename from `.js` to `.jsx` looked like a broken import. Now the bare name only counts if it is distinctive and no living file shares it, and renames are reported as reincarnations. Both cases have tests.

Honest notes on quality: the model is a 7B. It often admits "the reason is not recorded", but in the séance above it invented a reason ("the project's goals shifted") from a commit message that did not say that. That is why the git facts sit above every whisper. I have also not yet seen a real, verified broken import come out of a hauntings run on my own repos. The feature is covered by unit tests and by real runs that taught me what to filter out.

## Why Does Open Innovation Matter?

The files people delete are often the ones they would least like to paste into a hosted API: abandoned experiments, old client code, things with a bad commit message. Because the model runs on my machine, a repository's entire history can be read, questioned and turned into a graveyard page without any of it going anywhere. The only network call is to localhost, the HTML page loads nothing, and it works with the Wi-Fi off.

It is also a setting, not a dependency: `--model` takes any model Ollama can run. I did not benchmark closed models against this, so I will not claim it beats them. For this job, private and free to run was what mattered, and an open-weight 7B was enough.

## My Agent Session

<!-- TODO (optional): save this session with DevRelay and embed it. -->

## The Spirit of It

<!-- TODO: add one honest sentence about the moment it landed for you. Only you know whether it did. -->

## Prize Categories

<!-- TODO: only list a partner category if you actually used its technology. This project uses none, so consider removing this section. -->
