#!/usr/bin/env python3
"""Git Seance: let the files a repository deleted speak once more.

Every fact (author, dates, lifespan, last words) comes from git. A local
open-weight model, run through Ollama on localhost, only phrases it.
Standard library only; nothing leaves the machine.
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5-coder:7b-instruct"
MAX_EXCERPT_CHARS = 2500
MAX_FILE_BYTES = 200_000
SEP = "\x1f"


@dataclass
class Ghost:
    path: str
    born: datetime
    born_by: str
    born_msg: str
    died: datetime
    died_by: str
    died_msg: str
    died_commit: str
    lines: int
    last_words: str
    excerpt: str

    @property
    def days_lived(self):
        return max((self.died - self.born).days, 0)


def git(repo, *args, check=True):
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "git failed")
    return done.stdout


def parse_deletions(log_output):
    """Parse `git log --diff-filter=D --name-only` output into (commit, author, date, subject, path) rows."""
    rows, header = [], None
    for line in log_output.splitlines():
        if SEP in line:
            header = line.split(SEP)
        elif line.strip() and header:
            rows.append((*header, line.strip()))
    return rows


def birth_of(repo, commit, path):
    """First commit that added `path`, searching only history before its deletion."""
    out = git(repo, "log", f"{commit}^", "--diff-filter=A", "--follow",
              f"--format=%aI{SEP}%an{SEP}%s", "--", path, check=False)
    lines = [l for l in out.splitlines() if SEP in l]
    if not lines:
        return None
    date, author, subject = lines[-1].split(SEP)
    return datetime.fromisoformat(date), author, subject


def last_words_of(text):
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def exhume(repo, limit=5, min_lines=5):
    """Return the longest-lived deleted text files, oldest lives first."""
    log = git(repo, "log", "--diff-filter=D", "--name-only", "--no-renames",
              f"--format=%H{SEP}%an{SEP}%aI{SEP}%s")
    seen, ghosts = set(), []
    for commit, author, date, subject, path in parse_deletions(log):
        if path in seen:
            continue
        seen.add(path)
        blob = subprocess.run(["git", "-C", repo, "show", f"{commit}^:{path}"],
                              capture_output=True)
        if blob.returncode != 0 or b"\0" in blob.stdout or len(blob.stdout) > MAX_FILE_BYTES:
            continue
        text = blob.stdout.decode("utf-8", errors="replace")
        n_lines = len(text.splitlines())
        birth = birth_of(repo, commit, path)
        if n_lines < min_lines or not birth:
            continue
        born, born_by, born_msg = birth
        ghosts.append(Ghost(path, born, born_by, born_msg, datetime.fromisoformat(date),
                            author, subject, commit[:8], n_lines, last_words_of(text),
                            text[:MAX_EXCERPT_CHARS]))
    ghosts.sort(key=lambda g: (g.days_lived, g.lines), reverse=True)
    return ghosts[:limit]


def headstone(g):
    return "\n".join([
        f"  {g.path}",
        f"  born  {g.born:%Y-%m-%d}  by {g.born_by}: \"{g.born_msg}\"",
        f"  died  {g.died:%Y-%m-%d}  by {g.died_by}: \"{g.died_msg}\" ({g.died_commit})",
        f"  lived {g.days_lived} days, {g.lines} lines",
        f"  last words: {g.last_words}",
    ])


SYSTEM = (
    "You are the ghost of a deleted source file, speaking once from beyond the repository. "
    "Speak in first person, 5 to 7 sentences, calm and a little eerie, with some warmth. "
    "Use ONLY the facts and code you are given. Never invent names, dates, features or reasons. "
    "If you do not know why you were deleted, say you do not know. Do not use markdown."
)


def build_prompt(g):
    return (
        f"File: {g.path}\n"
        f"Born {g.born:%Y-%m-%d}, written by {g.born_by}, commit message \"{g.born_msg}\".\n"
        f"Deleted {g.died:%Y-%m-%d} by {g.died_by}, commit message \"{g.died_msg}\".\n"
        f"Lived {g.days_lived} days, {g.lines} lines. Last line: {g.last_words}\n\n"
        f"The beginning of my body:\n{g.excerpt}\n\n"
        "Speak as this file."
    )


def ask_model(prompt, model, url=OLLAMA_URL):
    body = json.dumps({
        "model": model, "stream": False,
        "options": {"temperature": 0.7, "seed": 31},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)["message"]["content"].strip()


def ofrenda(ghosts, whispers, repo):
    out = [f"# Ofrenda for {repo}", "",
           "Files this repository deleted, remembered from git history.", ""]
    for g, w in zip(ghosts, whispers):
        out += [f"## {g.path}", "", "```", headstone(g), "```", ""]
        if w:
            out += [f"> {w}".replace("\n", "\n> "), ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Let a repository's deleted files speak.")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--limit", type=int, default=3, help="how many ghosts to summon")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-model", action="store_true", help="headstones only, no model")
    ap.add_argument("--out", help="also write an ofrenda markdown file")
    args = ap.parse_args(argv)

    try:
        ghosts = exhume(args.repo, args.limit)
    except RuntimeError as e:
        sys.exit(f"seance: {e}")
    if not ghosts:
        sys.exit("The graveyard is empty: no deleted text files in this history.")

    whispers = []
    for g in ghosts:
        print(f"\n{headstone(g)}\n")
        whisper = None
        if not args.no_model:
            try:
                whisper = ask_model(build_prompt(g), args.model)
                print(whisper)
            except (urllib.error.URLError, OSError, KeyError) as e:
                print(f"  (the spirit did not answer: {e}; run with --no-model for headstones only)")
        whispers.append(whisper)
    if args.out:
        with open(args.out, "w") as f:
            f.write(ofrenda(ghosts, whispers, args.repo))
        print(f"\nOfrenda written to {args.out}")


if __name__ == "__main__":
    main()
