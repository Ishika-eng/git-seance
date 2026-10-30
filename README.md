# Git Séance

Let the files your repository deleted speak once more.

Git Séance digs through a repo's history for deleted text files and builds a headstone for each from git itself: who wrote it, who deleted it, when, why (the commit messages), how long it lived, and its last line. Then a local open-weight model, run through [Ollama](https://ollama.com) on localhost, lets the file say a few words in its own voice.

```
  pilot/run_poison_pilot.py
  born  2026-09-22  by Ishika: "Add ATMC engine, pilot experiments, and demo app"
  died  2026-10-10  by Ishika: "Add self-evolving coding assistant loop, ..." (574028e1)
  lived 18 days, 157 lines
  last words: main()

I was a program designed to explore how trust-aware mechanisms could help ...
```

Every fact on the headstone comes from git. The model only phrases it, and it is told not to invent reasons, so when history does not say why a file died, the ghost says it does not know. It can still over-read a commit message, so treat the voice as a remembrance, not a record.

## Run it

Python 3.10+ (standard library only), git, and Ollama with a model pulled.

```bash
ollama pull qwen2.5-coder:7b-instruct
python3 seance.py /path/to/repo --limit 3 --out ofrenda.md
python3 seance.py /path/to/repo --no-model        # headstones only, no model
python3 seance.py /path/to/repo --model gemma3:4b  # any local model
```

`--out` writes an ofrenda: a markdown file with every headstone and whisper.

## Privacy

The only network call is to `localhost:11434`. Your history, file contents and commit messages never leave the machine, which matters because the files people delete are often the ones they would not paste into a hosted API.

## Limits

- It lists files deleted outright. Renamed files are not treated as deaths, and files over 200 KB or containing binary data are skipped.
- Ghosts are ranked by how long they lived, then by size.
- The model sees only the first 2,500 characters of the file.
- Output varies by model. Tested with Qwen2.5-Coder 7B on an M3 Pro: about 9 seconds per ghost.

## Tests

```bash
PYTHONPATH=. python3 -m unittest test_seance
```

The tests build a throwaway git repo, so they need git but not Ollama.
