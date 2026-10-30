---
title: Git Séance: letting deleted files speak, with a model that never leaves my laptop
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26)*

## What I Built

Every repository has a graveyard: the files someone deleted. `git log` knows exactly who wrote each one, when it was born, when it died and what the commit message said at the funeral. Nobody ever reads it.

Git Séance exhumes them. It finds the longest-lived deleted files in a repo, builds a headstone for each from git alone (born, died, by whom, why, lifespan, last line), and then a local open-weight model lets the file say a few words from beyond the repository. The result can be saved as an ofrenda, a markdown file of remembrances.

I took the theme two ways at once: the spooky one (a file speaking from beyond `git rm`) and the Día de los Muertos one (honoring work that existed, mattered for a while, and was set down on purpose).

This is what it said for a file from my own college project, which lived 18 days:

```
  pilot/run_poison_pilot.py
  born  2026-09-22  by Ishika: "Add ATMC engine, pilot experiments, and demo app"
  died  2026-10-10  by Ishika: "Add self-evolving coding assistant loop, evaluation harness and Assistant UI" (574028e1)
  lived 18 days, 157 lines
  last words: main()

I was born to test a hypothesis about the effectiveness of a trust-aware retrieval
system in a controlled environment. My days were short, yet I played a crucial role
in understanding the dynamics of trust and memory in language models. [...]
I am gone, but my legacy lives on in the lessons learned and the groundwork laid
for future research.
```

## Demo

<!-- TODO: add a short screen recording of `python3 seance.py <repo>` running, or screenshots. Nothing is deployed; it is a command line tool. -->

## Code

{% embed https://github.com/Ishika-eng/git-seance %}

## How I Built It

- **Git does the remembering.** `git log --diff-filter=D` lists deletions. `git show <commit>^:<path>` recovers the last version, and a second `git log --diff-filter=A --follow` finds the birth. Lifespan, line count and last words are computed, never generated.
- **An open-weight model does the speaking.** Qwen2.5-Coder 7B Instruct (Apache 2.0) runs through Ollama at `localhost:11434`. The tool calls it with Python's standard library. There are no dependencies to install.
- **The model is fenced in.** The system prompt says to use only the facts given, never invent names, dates or reasons, and to admit when it does not know why the file was deleted. Facts are printed in the headstone separately from the voice, so you can always see which part is git and which part is the model.
- **It degrades gracefully.** If Ollama is not running, you still get headstones (`--no-model` does that on purpose).
- **Tested without a model.** Six unit tests build a throwaway git repo and check the facts, the skipping of binary and living files, the ofrenda output, and survival when the model is down.

Honest notes on quality: on two ghosts, one correctly said the reason for its deletion "is not recorded in history". The other said it was "replaced by a more advanced system", which is a plausible reading of the commit message but still an inference. A 7B model embellishes in a warm, ghostly voice, and I left that in because the headstone sits right above it.

## Why Does Open Innovation Matter?

The files people delete are often the ones they would least like to paste into a hosted API: abandoned experiments, old client code, things with a bad commit message. Because the model runs on my machine, a repository's whole history can be read by it without that history going anywhere. The only network call in the program is to localhost, and it works with the Wi-Fi off.

It is also a setting, not a dependency: `--model` takes any model Ollama can run, so I can swap models without changing a line. I did not benchmark closed models against this, so I will not claim it beats them. For this job, private and free to run was what mattered, and an open-weight 7B was enough.

## My Agent Session

<!-- TODO (optional): save this session with DevRelay and embed it. -->

## The Spirit of It

<!-- TODO: add one honest sentence about the moment it landed for you. Only you know whether it did. -->

## Prize Categories

<!-- TODO: only list a partner category if you actually used its technology. This project uses none so far, so consider removing this section. -->
