#!/usr/bin/env python3
"""Git Seance: let the files a repository deleted speak once more.

Every fact (author, dates, lifespan, last words, who still mentions the dead
file) comes from git. A local open-weight model, run through Ollama on
localhost, only gives the dead a voice. Standard library only; nothing leaves
the machine.
"""
import argparse
import collections
import html
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5-coder:7b-instruct"
MAX_EXCERPT_CHARS = 2500
MAX_FILE_BYTES = 200_000
MAX_SCAN = 400
SEP = "\x1f"
GENERIC_STEMS = {"index", "main", "test", "tests", "utils", "util", "config", "readme",
                 "common", "base", "core", "setup", "settings", "constants"}


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
    haunting: list = field(default_factory=list)
    reborn_as: str = None
    successor: tuple = None  # (path, similarity percent) of what replaced it

    @property
    def days_lived(self):
        return max((self.died - self.born).days, 0)

    @property
    def cause(self):
        return cause_of_death(self.died_msg)


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


def birth_of(repo, last_rev, path):
    """First commit that added `path`, searching from the last revision that still had it."""
    out = git(repo, "log", last_rev, "--diff-filter=A", "--follow",
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


def alive_at_head(repo, path):
    return subprocess.run(["git", "-C", repo, "cat-file", "-e", f"HEAD:{path}"],
                          capture_output=True).returncode == 0


def exhume(repo, min_lines=5):
    """Every deleted text file that is still dead, longest-lived first."""
    log = git(repo, "log", "--diff-filter=D", "--name-only", "--no-renames",
              f"--format=%H{SEP}%an{SEP}%aI{SEP}%s")
    seen, ghosts = set(), []
    for commit, author, date, subject, path in parse_deletions(log)[:MAX_SCAN]:
        if path in seen:
            continue
        seen.add(path)
        if alive_at_head(repo, path):
            continue
        blob = subprocess.run(["git", "-C", repo, "show", f"{commit}^:{path}"],
                              capture_output=True)
        if blob.returncode != 0 or b"\0" in blob.stdout or len(blob.stdout) > MAX_FILE_BYTES:
            continue
        text = blob.stdout.decode("utf-8", errors="replace")
        n_lines = len(text.splitlines())
        birth = birth_of(repo, f"{commit}^", path)
        if n_lines < min_lines or not birth:
            continue
        born, born_by, born_msg = birth
        ghosts.append(Ghost(path, born, born_by, born_msg, datetime.fromisoformat(date),
                            author, subject, commit, n_lines, last_words_of(text),
                            text[:MAX_EXCERPT_CHARS]))
    ghosts.sort(key=lambda g: (g.days_lived, g.lines), reverse=True)
    return ghosts


# --- hauntings: living code that still points at the dead -------------------

def living_paths(repo):
    return git(repo, "ls-files").splitlines()


def reincarnation(ghost, paths):
    """A living file with the same path but another extension: the ghost was renamed, not killed."""
    stem = ghost.path.rsplit(".", 1)[0]
    return next((p for p in paths if p != ghost.path and p.rsplit(".", 1)[0] == stem), None)


def haunt_tokens(path, living):
    """What to search for: the full path, then the bare name only if it is distinctive and unshared."""
    base = posixpath.basename(path)
    stem = base.rsplit(".", 1)[0]
    tokens = []
    if path != base or base not in living:  # a root-level name shared with a living file is ambiguous
        tokens = [path, path.rsplit(".", 1)[0]]
    if len(stem) >= 8 and stem.lower() not in GENERIC_STEMS and base not in living:
        tokens += [base, stem]
    return list(dict.fromkeys(tokens))


def hauntings(repo, ghost, paths=None, limit=5, cached=False):
    """Lines that still mention the dead file: (path, line number, text).

    Searches HEAD, or the staged index when `cached` (for a deletion not yet committed)."""
    paths = living_paths(repo) if paths is None else paths
    if reincarnation(ghost, paths):
        return []
    living = {posixpath.basename(p) for p in paths}
    tree, prefix = ("--cached", 0) if cached else ("HEAD", len("HEAD:"))
    found, seen = [], set()
    for token in haunt_tokens(ghost.path, living):
        out = git(repo, "grep", "-n", "-I", "-F", "-e", token, tree, check=False)
        for line in out.splitlines():
            parts = line[prefix:].split(":", 2)
            if len(parts) != 3 or parts[0] == ghost.path or not parts[1].isdigit():
                continue
            key = (parts[0], parts[1])
            if key not in seen:
                seen.add(key)
                found.append((parts[0], int(parts[1]), parts[2].strip()[:90]))
    return found[:limit]


# --- successors and zombies ---------------------------------------------------

def line_set(text):
    return {l.strip() for l in text.splitlines() if len(l.strip()) > 2}


def read_blob(repo, spec):
    blob = subprocess.run(["git", "-C", repo, "show", spec], capture_output=True)
    if blob.returncode != 0 or b"\0" in blob.stdout or len(blob.stdout) > MAX_FILE_BYTES:
        return None
    return blob.stdout.decode("utf-8", errors="replace")


def find_successor(repo, ghost, min_similarity=30):
    """What replaced the file: a git rename in the deleting commit, or the file added in that
    same commit whose lines overlap most with it. Returns (path, similarity percent) or None."""
    out = git(repo, "diff-tree", "-r", "-M30%", "--name-status", "--no-commit-id",
              ghost.died_commit, check=False)
    added = []
    for line in out.splitlines():
        parts = line.split("\t")
        if parts[0].startswith("R") and len(parts) == 3 and parts[1] == ghost.path:
            return parts[2], int(parts[0][1:])
        if parts[0] == "A" and len(parts) == 2:
            added.append(parts[1])
    dead = line_set(read_blob(repo, f"{ghost.died_commit}^:{ghost.path}") or "")
    best_path, best = None, 0.0
    for path in added[:20]:
        text = read_blob(repo, f"{ghost.died_commit}:{path}")
        new = line_set(text or "")
        if dead and new:
            overlap = len(dead & new) / len(dead | new)
            if overlap > best:
                best_path, best = path, overlap
    if best_path and best * 100 >= min_similarity:
        return best_path, round(best * 100)
    return None


def zombies(repo):
    """Files that were deleted and are alive again, with how many times they died."""
    log = git(repo, "log", "--diff-filter=D", "--name-only", "--no-renames",
              f"--format=%H{SEP}%an{SEP}%aI{SEP}%s")
    deaths = collections.Counter(row[4] for row in parse_deletions(log))
    alive = set(living_paths(repo))
    return sorted(((p, n) for p, n in deaths.items() if p in alive), key=lambda t: (-t[1], t[0]))


# --- last rites: a warning before a deletion is committed ---------------------

HOOK_MARK = "# installed by git-seance"


def staged_ghosts(repo):
    """Files staged for deletion right now, as ghosts with hauntings searched in the index."""
    names = git(repo, "diff", "--cached", "--name-only", "--diff-filter=D", "--no-renames").splitlines()
    who = git(repo, "config", "user.name", check=False).strip() or "you"
    now = datetime.now().astimezone()
    paths = living_paths(repo)
    ghosts = []
    for path in names:
        text = read_blob(repo, f"HEAD:{path}")
        birth = birth_of(repo, "HEAD", path)
        if text is None or not birth:
            continue
        born, born_by, born_msg = birth
        g = Ghost(path, born, born_by, born_msg, now, who, "staged deletion", "staged",
                  len(text.splitlines()), last_words_of(text), text[:MAX_EXCERPT_CHARS])
        g.reborn_as = reincarnation(g, paths)
        g.haunting = hauntings(repo, g, paths, cached=True)
        ghosts.append(g)
    return ghosts


def last_rites_text(ghosts):
    n = len(ghosts)
    lines = [f"  LAST RITES: {n} file{'s' if n != 1 else ''} staged for deletion."]
    for g in ghosts:
        lines += ["", f"  {g.path}  ({g.lines} lines, born {g.born:%Y-%m-%d} by {g.born_by}, "
                      f"lived {g.days_lived} days)", haunting_text(g)]
    return "\n".join(lines)


def install_hook(repo):
    """Install a pre-commit hook that performs the last rites. Never overwrites a foreign hook."""
    hook = git(repo, "rev-parse", "--git-path", "hooks/pre-commit").strip()
    hook = hook if os.path.isabs(hook) else os.path.join(repo, hook)
    if os.path.exists(hook):
        with open(hook) as f:
            if HOOK_MARK not in f.read():
                raise RuntimeError(f"{hook} already exists and is not ours; not touching it")
    os.makedirs(os.path.dirname(hook), exist_ok=True)
    with open(hook, "w") as f:
        f.write("#!/bin/sh\n" + HOOK_MARK + "\n"
                f"exec python3 {shlex.quote(os.path.abspath(__file__))} --last-rites "
                '"$(git rev-parse --show-toplevel)"\n')
    os.chmod(hook, 0o755)
    return hook


# --- the coroner -------------------------------------------------------------

CAUSES = [
    ("replaced", ("replace", "rewrite", "rework", "supersede", "instead of")),
    ("refactor", ("refactor", "restructure", "reorgan", "move", "rename", "split", "consolidat")),
    ("cleanup", ("remove", "delete", "clean", "drop", "prune", "unused", "obsolete", "stale")),
    ("merge", ("merge",)),
    ("fix or revert", ("fix", "bug", "revert")),
]
COLLATERAL_STARTS = ("add", "implement", "introduce", "create", "build")


def cause_of_death(message):
    """A heuristic guess from the deleting commit's message, never a verdict."""
    m = message.lower()
    if m.startswith(COLLATERAL_STARTS):
        return "collateral damage"
    for label, words in CAUSES:
        if any(re.search(r"\b" + w, m) for w in words):
            return label
    return "unrecorded"


def coroner(ghosts, zombie_list=None):
    killers = collections.Counter(g.died_by for g in ghosts)
    graves = collections.Counter(g.died_commit for g in ghosts)
    grave, grave_n = graves.most_common(1)[0]
    grave_msg = next(g.died_msg for g in ghosts if g.died_commit == grave)
    return {
        "total": len(ghosts),
        "avg_days": sum(g.days_lived for g in ghosts) / len(ghosts),
        "longest": ghosts[0],
        "killers": killers.most_common(3),
        "mass_grave": (grave[:8], grave_n, grave_msg),
        "causes": collections.Counter(g.cause for g in ghosts).most_common(),
        "zombies": zombie_list or [],
    }


def coroner_text(r):
    g = r["longest"]
    grave, n, msg = r["mass_grave"]
    zombie_line = ["  Zombies (died, then came back): "
                   + ", ".join(f"{p} ({n}x)" for p, n in r["zombies"])] if r.get("zombies") else []
    return "\n".join([
        f"  {r['total']} souls lie here, living {r['avg_days']:.0f} days on average.",
        f"  Longest life: {g.path} ({g.days_lived} days).",
        "  Hands that deleted the most: " + ", ".join(f"{k} ({v})" for k, v in r["killers"]),
        f"  Worst night: commit {grave} took {n} file{'s' if n != 1 else ''} at once: \"{msg}\"",
        "  Probable causes (guessed from commit messages): "
        + ", ".join(f"{k} {v}" for k, v in r["causes"]),
        *zombie_line,
    ])


# --- presentation --------------------------------------------------------------

def paint(text, code):
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        return f"\x1b[{code}m{text}\x1b[0m"
    return text


def clip(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def tombstone_art(g, width=58):
    rows = ["R . I . P .", "", clip(g.path, width), f"{g.born:%Y-%m-%d} - {g.died:%Y-%m-%d}",
            f"lived {g.days_lived} days, {g.lines} lines", "",
            clip(f"\"{g.last_words}\"", width), f"cause of death: {g.cause}"]
    if g.successor:
        rows.append(clip(f"succeeded by {g.successor[0]} ({g.successor[1]}%)", width))
    inner = max(len(r) for r in rows) + 4
    body = ["│" + r.center(inner) + "│" for r in rows]
    return "\n".join(["  ╭" + "─" * inner + "╮", *["  " + b for b in body],
                      "  ╰" + "─" * inner + "╯"])


def headstone(g):
    return "\n".join([
        f"  {g.path}",
        f"  born  {g.born:%Y-%m-%d}  by {g.born_by}: \"{g.born_msg}\"",
        f"  died  {g.died:%Y-%m-%d}  by {g.died_by}: \"{g.died_msg}\" ({g.died_commit[:8]})",
        f"  lived {g.days_lived} days, {g.lines} lines",
        f"  last words: {g.last_words}",
        *([f"  successor: {g.successor[0]} ({g.successor[1]}% similar, same commit)"]
          if g.successor else []),
    ])


def haunting_text(g):
    if g.reborn_as:
        return f"  Not truly gone: it lives on as {g.reborn_as}."
    if not g.haunting:
        return "  No living code mentions it. It rests."
    lines = [f"  Still haunting {len(g.haunting)} place{'s' if len(g.haunting) != 1 else ''}:"]
    lines += [f"    {p}:{n}  {t}" for p, n, t in g.haunting]
    return "\n".join(lines)


SYSTEM = (
    "You are the ghost of a deleted source file, speaking once from beyond the repository. "
    "Speak in first person, 5 to 7 sentences, calm and a little eerie, with some warmth. "
    "Use ONLY the facts and code you are given. Never invent names, dates, features or reasons. "
    "If you do not know why you were deleted, say you do not know. Do not use markdown."
)

TALK_SYSTEM = (
    "You are the ghost of a deleted source file, answering questions from the living in a seance. "
    "Stay in character: first person, short answers of 2 to 4 sentences, a little eerie, with warmth. "
    "Answer ONLY from the facts and code below. If asked about anything not in them, say you do not "
    "remember. Never invent names, dates, features or reasons. Do not use markdown."
)


def build_prompt(g):
    return (
        f"File: {g.path}\n"
        f"Born {g.born:%Y-%m-%d}, written by {g.born_by}, commit message \"{g.born_msg}\".\n"
        f"Deleted {g.died:%Y-%m-%d} by {g.died_by}, commit message \"{g.died_msg}\".\n"
        f"Lived {g.days_lived} days, {g.lines} lines. Last line: {g.last_words}\n"
        + (f"Living code that still mentions me: {', '.join(f'{p}:{n}' for p, n, _ in g.haunting)}.\n"
           if g.haunting else "")
        + (f"The commit that deleted me also added {g.successor[0]}, {g.successor[1]}% similar to me.\n"
           if g.successor else "")
        + f"\nThe beginning of my body:\n{g.excerpt}\n\nSpeak as this file."
    )


def chat(messages, model, on_token=None, url=OLLAMA_URL):
    """Stream a reply from a local Ollama model, passing each token to `on_token`."""
    body = json.dumps({"model": model, "stream": True,
                       "options": {"temperature": 0.7, "seed": 31},
                       "messages": messages}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    parts = []
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            if not raw.strip():
                continue
            chunk = json.loads(raw)
            token = chunk.get("message", {}).get("content", "")
            if token:
                parts.append(token)
                if on_token:
                    on_token(token)
            if chunk.get("done"):
                break
    return "".join(parts).strip()


def talk(g, model, input_fn=input, say=print, chat_fn=chat):
    """A seance: ask a deleted file questions until the living say goodbye."""
    messages = [{"role": "system", "content": TALK_SYSTEM + "\n\n" + build_prompt(g)}]
    say(paint("  The candles gutter. Ask it anything. An empty line or 'goodbye' ends the seance.", "2"))
    while True:
        try:
            question = input_fn(paint("\nyou > ", "36")).strip()
        except EOFError:
            break
        if not question or question.lower() in {"exit", "quit", "goodbye", "bye"}:
            break
        messages.append({"role": "user", "content": question})
        print(paint(f"{posixpath.basename(g.path)} > ", "35"), end="", flush=True)
        try:
            reply = chat_fn(messages, model, on_token=lambda t: print(t, end="", flush=True))
        except (urllib.error.URLError, OSError, ValueError) as e:
            say(f"(the spirit did not answer: {e})")
            messages.pop()
            continue
        print()
        messages.append({"role": "assistant", "content": reply})
    say(paint("\n  The spirit fades.", "2"))


def raise_dead(repo, ghost, into):
    """Write the file's last version under `into`. The repository itself is not touched."""
    root = os.path.abspath(into)
    dest = os.path.abspath(os.path.join(root, ghost.path))
    if not dest.startswith(root + os.sep):
        raise RuntimeError(f"refusing to write outside {into}: {ghost.path}")
    blob = subprocess.run(["git", "-C", repo, "show", f"{ghost.died_commit}^:{ghost.path}"],
                          capture_output=True)
    if blob.returncode != 0:
        raise RuntimeError(blob.stderr.decode(errors="replace").strip() or "git show failed")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(blob.stdout)
    return dest


def ofrenda(ghosts, whispers, repo, report=None):
    out = [f"# Ofrenda for {repo}", "",
           "Files this repository deleted, remembered from git history.", ""]
    if report:
        out += ["## The coroner's report", "", "```", coroner_text(report), "```", ""]
    for g, w in zip(ghosts, whispers):
        out += [f"## {g.path}", "", "```", tombstone_art(g), "", headstone(g), "",
                haunting_text(g), "```", ""]
        if w:
            out += [f"> {w}".replace("\n", "\n> "), ""]
    return "\n".join(out)


def lifespan_svg(ghosts, width=900, limit=30):
    """One bar per ghost, from birth (green) to death (red dot), oldest birth first."""
    ghosts = sorted(ghosts[:limit], key=lambda g: g.born)
    if not ghosts:
        return ""
    t0, t1 = min(g.born for g in ghosts), max(g.died for g in ghosts)
    span = max((t1 - t0).total_seconds(), 86400)
    row, pad = 14, 22
    height = pad * 2 + row * len(ghosts)

    def x(moment):
        return 12 + (moment - t0).total_seconds() / span * (width - 24)

    bars = []
    for i, g in enumerate(ghosts):
        y = pad + i * row
        x1, x2 = x(g.born), max(x(g.died), x(g.born) + 4)
        bars.append(f'<g><title>{html.escape(g.path)}: {g.days_lived} days</title>'
                    f'<line x1="{x1:.1f}" y1="{y}" x2="{x2:.1f}" y2="{y}"/>'
                    f'<circle cx="{x2:.1f}" cy="{y}" r="4"/></g>')
    return (f'<svg class="lifespans" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="Lifespan of each deleted file">'
            f'<text x="12" y="14">{t0:%Y-%m-%d}</text>'
            f'<text x="{width - 12}" y="14" text-anchor="end">{t1:%Y-%m-%d}</text>'
            + "".join(bars) + "</svg>")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graveyard of {{REPO}}</title>
<style>
:root{--bg1:#05060d;--bg2:#141226;--stone:#2a2a3c;--stone2:#3a3a52;--text:#d8d6e6;--dim:#8d8aa8;--glow:#9ef0c4;--blood:#c0485a}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:var(--text);font:16px/1.55 Georgia,'Times New Roman',serif;
background:radial-gradient(circle at 80% 8%,#2b2850 0,transparent 22%),linear-gradient(var(--bg1),var(--bg2));overflow-x:hidden}
.moon{position:fixed;top:36px;right:9vw;width:70px;height:70px;border-radius:50%;background:#efe9d2;box-shadow:0 0 60px 18px #efe9d255;opacity:.9}
.fog{position:fixed;left:-50%;width:200%;height:240px;bottom:0;pointer-events:none;
background:radial-gradient(ellipse at center,#c8c6e022 0,transparent 65%);animation:drift 38s linear infinite}
.fog.b{bottom:50px;animation-duration:55s;animation-direction:reverse;opacity:.7}
@keyframes drift{from{transform:translateX(-12%)}to{transform:translateX(12%)}}
header,main,footer{position:relative;max-width:1000px;margin:0 auto;padding:0 20px}
header{padding-top:70px}
h1{font-size:clamp(2rem,6vw,3.4rem);margin:0;letter-spacing:.04em;font-weight:400;animation:flicker 6s infinite}
@keyframes flicker{0%,18%,22%,60%,64%,100%{opacity:1}20%,62%{opacity:.55}}
.sub{color:var(--dim);margin:.4rem 0 1.4rem}
.coroner{border-left:3px solid var(--blood);padding:.4rem 1rem;background:#ffffff08;white-space:pre-wrap;font:14px/1.6 ui-monospace,Menlo,monospace;color:#cfcbe6}
.life{margin-top:22px}
.life h2{font:400 .95rem Georgia,serif;color:var(--dim);margin:0 0 4px}
.lifespans{width:100%;height:auto;display:block}
.lifespans line{stroke:var(--glow);stroke-width:3;stroke-linecap:round;opacity:.65}
.lifespans circle{fill:var(--blood)}
.lifespans text{fill:var(--dim);font:11px ui-monospace,Menlo,monospace}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:28px;margin:34px 0 120px;align-items:start}
.stone{background:linear-gradient(var(--stone2),var(--stone));border-radius:130px 130px 6px 6px;padding:58px 20px 20px;
text-align:center;box-shadow:inset 0 0 30px #0008,0 10px 30px #0008;transition:transform .25s,box-shadow .25s;position:relative}
.stone:hover,.stone[open]{transform:translateY(-6px);box-shadow:inset 0 0 30px #0008,0 0 36px #9ef0c433,0 10px 30px #0008}
.rip{letter-spacing:.35em;color:var(--dim);font-size:.8rem}
.name{font:600 .95rem ui-monospace,Menlo,monospace;word-break:break-all;margin:.5rem 0}
.dates{color:var(--dim);font-size:.85rem}
.epi{margin:.8rem 0;font-style:italic;color:var(--glow);word-break:break-word}
.tag{display:inline-block;font-size:.72rem;border:1px solid var(--dim);border-radius:99px;padding:1px 10px;color:var(--dim)}
.haunt{color:var(--blood);font-size:.82rem;margin-top:.6rem}
summary{cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
.listen{color:var(--dim);margin-top:.8rem;font-size:.85rem}
.stone:hover .listen{color:var(--glow)}
.more{text-align:left;font-size:.88rem;margin-top:.7rem;border-top:1px solid #ffffff18;padding-top:.7rem}
.whisper{font-style:italic;color:#e6e1ff;white-space:pre-wrap}
code{font:12px ui-monospace,Menlo,monospace;color:#bdb8dd;white-space:pre-wrap;word-break:break-word;display:block;margin-bottom:.6rem}
footer{padding-bottom:60px;color:var(--dim);font-size:.85rem}
@media(prefers-reduced-motion:reduce){.fog,h1{animation:none}.stone{transition:none}}
</style></head><body>
<div class="moon"></div><div class="fog"></div><div class="fog b"></div>
<header><h1>Graveyard of {{REPO}}</h1>
<p class="sub">Every fact below comes from git. Only the whispers come from a model, and it runs on this machine.</p>
<div class="coroner">{{CORONER}}</div>
<div class="life">{{LIFE}}</div></header>
<main><div class="grid">{{STONES}}</div></main>
<footer>Exhumed by Git Séance. Click a stone to hear it speak.</footer>
</body></html>"""


def graveyard_html(ghosts, whispers, repo, report=None, lifespans=None):
    e = html.escape
    stones = []
    for g, w in zip(ghosts, whispers):
        haunt = (f'<div class="haunt">still haunting {len(g.haunting)} place'
                 f'{"s" if len(g.haunting) != 1 else ""}</div>') if g.haunting else ""
        more = [f"<code>{e(headstone(g))}</code>"]
        if g.haunting:
            more.append("<code>" + e("\n".join(f"{p}:{n}  {t}" for p, n, t in g.haunting)) + "</code>")
        if w:
            more.append(f'<p class="whisper">{e(w)}</p>')
        stones.append(
            '<details class="stone"><summary><div class="rip">R . I . P .</div>'
            f'<div class="name">{e(g.path)}</div>'
            f'<div class="dates">{g.born:%Y-%m-%d} – {g.died:%Y-%m-%d} · {g.days_lived} days</div>'
            f'<div class="epi">“{e(clip(g.last_words, 70))}”</div>'
            f'<span class="tag">{e(g.cause)}</span>{haunt}'
            f'<div class="listen">listen ▾</div></summary><div class="more">{"".join(more)}</div></details>')
    coroner_block = "\n".join(l.strip() for l in coroner_text(report).splitlines()) if report else ""
    return (PAGE.replace("{{REPO}}", e(repo))
            .replace("{{CORONER}}", e(coroner_block))
            .replace("{{LIFE}}", ("<h2>Every ghost, from birth (green) to death (red)</h2>"
                                  + lifespan_svg(lifespans)) if lifespans else "")
            .replace("{{STONES}}", "\n".join(stones)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Let a repository's deleted files speak.")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--limit", type=int, default=3, help="how many ghosts to summon")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-model", action="store_true", help="facts only, no model")
    ap.add_argument("--out", help="also write an ofrenda markdown file")
    ap.add_argument("--html", help="also write a self-contained spooky graveyard page")
    ap.add_argument("--talk", type=int, nargs="?", const=1, metavar="N",
                    help="hold a seance with ghost number N (default 1)")
    ap.add_argument("--raise", dest="raise_path", metavar="PATH",
                    help="restore a deleted file's last version (see --into)")
    ap.add_argument("--into", default="resurrected", help="folder that --raise writes to")
    ap.add_argument("--last-rites", action="store_true",
                    help="warn about files staged for deletion that living code still mentions")
    ap.add_argument("--strict", action="store_true", help="with --last-rites, exit 1 if anything is haunted")
    ap.add_argument("--eulogy", action="store_true", help="with --last-rites, let each file say goodbye")
    ap.add_argument("--install-hook", action="store_true",
                    help="install a pre-commit hook that performs the last rites")
    args = ap.parse_args(argv)

    try:
        git(args.repo, "rev-parse", "--git-dir")
    except RuntimeError:
        sys.exit(f"seance: {args.repo} is not a git repository, so there is no history to dig through")

    if args.install_hook:
        try:
            print(f"  The hook is in place: {install_hook(args.repo)}")
        except RuntimeError as e:
            sys.exit(f"seance: {e}")
        print("  Stage a deletion and commit; to remove it, delete that file.")
        return

    if args.last_rites:
        try:
            staged = staged_ghosts(args.repo)
        except RuntimeError as e:
            sys.exit(f"seance: {e}")
        if not staged:
            return
        print(last_rites_text(staged))
        if args.eulogy and not args.no_model:
            for g in staged:
                print(paint(f"\n  {g.path} says:", "35"))
                try:
                    chat([{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": build_prompt(g)}], args.model,
                         on_token=lambda t: print(paint(t, "3"), end="", flush=True))
                    print()
                except (urllib.error.URLError, OSError, ValueError) as e:
                    print(f"  (the spirit did not answer: {e})")
        if args.strict and any(g.haunting for g in staged):
            sys.exit(1)
        return

    try:
        everyone = exhume(args.repo)
    except RuntimeError as e:
        sys.exit(f"seance: {e}")
    if not everyone:
        sys.exit("The graveyard is empty: no deleted text files in this history.")

    if args.raise_path:
        match = [g for g in everyone if g.path == args.raise_path]
        if not match:
            sys.exit(f"seance: no ghost named {args.raise_path}. Run without --raise to see them.")
        try:
            dest = raise_dead(args.repo, match[0], args.into)
        except RuntimeError as e:
            sys.exit(f"seance: {e}")
        print(paint(f"  {args.raise_path} stirs, and lives again at {dest}", "35"))
        print(f"  Its last words were: {match[0].last_words}")
        return

    if args.talk is not None:
        if not 1 <= args.talk <= len(everyone):
            sys.exit(f"seance: pick a ghost from 1 to {len(everyone)}")
        g = everyone[args.talk - 1]
        paths = living_paths(args.repo)
        g.reborn_as = reincarnation(g, paths)
        g.haunting = hauntings(args.repo, g, paths)
        g.successor = find_successor(args.repo, g)
        print("\n" + paint(tombstone_art(g), "90") + "\n\n" + haunting_text(g))
        talk(g, args.model)
        return

    report = coroner(everyone, zombies(args.repo)[:3])
    ghosts = everyone[:args.limit]
    paths = living_paths(args.repo)
    for g in ghosts:
        g.reborn_as = reincarnation(g, paths)
        g.haunting = hauntings(args.repo, g, paths)
        g.successor = find_successor(args.repo, g)

    print(paint("\n  THE CORONER'S REPORT", "31;1") + "\n" + coroner_text(report))
    whispers = []
    for g in ghosts:
        print("\n" + paint(tombstone_art(g), "90") + "\n\n" + headstone(g) + "\n\n"
              + haunting_text(g) + "\n")
        whisper = None
        if not args.no_model:
            try:
                whisper = chat([{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": build_prompt(g)}], args.model,
                               on_token=lambda t: print(paint(t, "3"), end="", flush=True))
                print()
            except (urllib.error.URLError, OSError, ValueError) as e:
                print(f"  (the spirit did not answer: {e}; run with --no-model for facts only)")
        whispers.append(whisper)
    if args.out:
        with open(args.out, "w") as f:
            f.write(ofrenda(ghosts, whispers, args.repo, report))
        print(f"\nOfrenda written to {args.out}")
    if args.html:
        name = os.path.basename(os.path.abspath(args.repo))
        with open(args.html, "w") as f:
            f.write(graveyard_html(ghosts, whispers, name, report, lifespans=everyone))
        print(f"Graveyard written to {args.html}")


if __name__ == "__main__":
    main()
