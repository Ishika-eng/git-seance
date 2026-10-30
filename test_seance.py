import os
import subprocess
import tempfile
import unittest
from unittest import mock

import seance


def run(repo, *args, date=None, author="Ada"):
    env = {**os.environ, "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": "a@x.io",
           "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": "a@x.io"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=env)


def commit(repo, msg, date, author="Ada"):
    run(repo, "add", "-A", author=author)
    run(repo, "commit", "-m", msg, date=date, author=author)


def write(repo, name, text, mode="w"):
    path = os.path.join(repo, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as f:
        f.write(text)


class SeanceTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.repo = self.dir.name
        run(self.repo, "init", "-q")
        body = "".join(f"line {i}\n" for i in range(10)) + "print('bye')\n"
        write(self.repo, "legacy_importer.py", body)
        write(self.repo, "blob.bin", b"\0\1\2" * 50, "wb")
        write(self.repo, "keep.py", "x\n" * 10)
        write(self.repo, "README.md", "Run legacy_importer.py first.\n")
        commit(self.repo, "Add old things", "2024-01-01T12:00:00")
        run(self.repo, "rm", "-q", "legacy_importer.py", "blob.bin")
        commit(self.repo, "Remove the legacy script", "2024-03-01T12:00:00", author="Grace")

    def tearDown(self):
        self.dir.cleanup()

    def test_finds_deleted_text_file_with_facts(self):
        ghosts = seance.exhume(self.repo)
        self.assertEqual([g.path for g in ghosts], ["legacy_importer.py"])
        g = ghosts[0]
        self.assertEqual(g.born_by, "Ada")
        self.assertEqual(g.died_by, "Grace")
        self.assertEqual(g.died_msg, "Remove the legacy script")
        self.assertEqual(g.days_lived, 60)
        self.assertEqual(g.last_words, "print('bye')")
        self.assertEqual(g.lines, 11)

    def test_binary_and_living_files_are_skipped(self):
        paths = [g.path for g in seance.exhume(self.repo)]
        self.assertNotIn("blob.bin", paths)
        self.assertNotIn("keep.py", paths)

    def test_a_file_brought_back_is_not_a_ghost(self):
        write(self.repo, "legacy_importer.py", "back\n" * 10)
        commit(self.repo, "Restore it", "2024-04-01T12:00:00")
        self.assertEqual(seance.exhume(self.repo), [])

    def test_hauntings_find_living_mentions(self):
        g = seance.exhume(self.repo)[0]
        found = seance.hauntings(self.repo, g)
        self.assertEqual(found, [("README.md", 1, "Run legacy_importer.py first.")])

    def test_a_name_shared_with_a_living_file_is_not_blamed_on_the_ghost(self):
        write(self.repo, "other/legacy_importer.py", "alive\n" * 10)
        commit(self.repo, "Another importer", "2024-04-01T12:00:00")
        g = seance.exhume(self.repo)[0]
        self.assertEqual(seance.hauntings(self.repo, g), [])

    def test_a_full_path_reference_is_a_haunting_even_for_a_short_name(self):
        write(self.repo, "svc/auth.js", "a\n" * 10)
        write(self.repo, "app.js", "const a = require('./svc/auth');\n")
        commit(self.repo, "Add auth", "2024-02-01T12:00:00")
        run(self.repo, "rm", "-q", "svc/auth.js")
        commit(self.repo, "Remove auth", "2024-06-01T12:00:00")
        g = [x for x in seance.exhume(self.repo) if x.path == "svc/auth.js"][0]
        self.assertEqual(seance.hauntings(self.repo, g),
                         [("app.js", 1, "const a = require('./svc/auth');")])

    def test_a_renamed_extension_is_a_reincarnation_not_a_haunting(self):
        write(self.repo, "hooks/useThing.js", "a\n" * 10)
        write(self.repo, "app.js", "import x from './hooks/useThing';\n")
        commit(self.repo, "Add hook", "2024-02-01T12:00:00")
        run(self.repo, "mv", "hooks/useThing.js", "hooks/useThing.jsx")
        commit(self.repo, "Use JSX", "2024-06-01T12:00:00")
        g = [x for x in seance.exhume(self.repo) if x.path == "hooks/useThing.js"][0]
        paths = seance.living_paths(self.repo)
        self.assertEqual(seance.reincarnation(g, paths), "hooks/useThing.jsx")
        self.assertEqual(seance.hauntings(self.repo, g, paths), [])

    def test_no_hauntings_when_nothing_mentions_it(self):
        write(self.repo, "README.md", "Nothing here.\n")
        commit(self.repo, "Edit readme", "2024-05-01T12:00:00")
        self.assertEqual(seance.hauntings(self.repo, seance.exhume(self.repo)[0]), [])

    def test_cause_of_death_is_a_labelled_guess(self):
        c = seance.cause_of_death
        self.assertEqual(c("Add new engine and drop old one"), "collateral damage")
        self.assertEqual(c("Rewrite the parser"), "replaced")
        self.assertEqual(c("Remove dead code"), "cleanup")
        self.assertEqual(c("Reorganise folders"), "refactor")
        self.assertEqual(c("wip"), "unrecorded")

    def test_coroner_names_killer_and_mass_grave(self):
        write(self.repo, "second.py", "y\n" * 10)
        write(self.repo, "third.py", "z\n" * 10)
        commit(self.repo, "Add more", "2024-04-01T12:00:00")
        run(self.repo, "rm", "-q", "second.py", "third.py")
        commit(self.repo, "Clean up", "2024-05-01T12:00:00", author="Grace")
        report = seance.coroner(seance.exhume(self.repo))
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["killers"][0], ("Grace", 3))
        self.assertEqual(report["mass_grave"][1], 2)
        self.assertIn("3 souls", seance.coroner_text(report))

    def test_raise_restores_last_version_outside_the_repo(self):
        g = seance.exhume(self.repo)[0]
        with tempfile.TemporaryDirectory() as out:
            dest = seance.raise_dead(self.repo, g, out)
            with open(dest) as f:
                self.assertTrue(f.read().endswith("print('bye')\n"))
        self.assertFalse(os.path.exists(os.path.join(self.repo, "legacy_importer.py")))

    def test_raise_refuses_paths_that_escape_the_folder(self):
        g = seance.exhume(self.repo)[0]
        g.path = "../../evil.py"
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaises(RuntimeError):
                seance.raise_dead(self.repo, g, out)

    def test_prompt_contains_git_facts_and_hauntings(self):
        g = seance.exhume(self.repo)[0]
        g.haunting = seance.hauntings(self.repo, g)
        prompt = seance.build_prompt(g)
        self.assertIn("Remove the legacy script", prompt)
        self.assertIn("Lived 60 days", prompt)
        self.assertIn("README.md:1", prompt)

    def test_tombstone_art_is_a_closed_box(self):
        art = seance.tombstone_art(seance.exhume(self.repo)[0]).splitlines()
        self.assertEqual(len({len(l) for l in art}), 1)
        self.assertIn("R . I . P .", art[1])

    def test_ofrenda_includes_report_whisper_and_headstone(self):
        ghosts = seance.exhume(self.repo)
        text = seance.ofrenda(ghosts, ["I remember."], "demo", seance.coroner(ghosts))
        self.assertIn("## legacy_importer.py", text)
        self.assertIn("> I remember.", text)
        self.assertIn("coroner's report", text)

    def test_html_escapes_everything_from_history(self):
        g = seance.exhume(self.repo)[0]
        g.died_msg = '<script>alert("x")</script>'
        page = seance.graveyard_html([g], ["<b>boo</b>"], "demo", seance.coroner([g]))
        self.assertNotIn("<script>", page)
        self.assertNotIn("<b>boo</b>", page)
        self.assertIn("&lt;b&gt;boo&lt;/b&gt;", page)
        self.assertIn("legacy_importer.py", page)

    def test_talk_keeps_the_conversation_and_ends_on_goodbye(self):
        g = seance.exhume(self.repo)[0]
        answers = iter(["why did you die?", "what did you do?", "goodbye"])
        seen = []

        def fake_chat(messages, model, on_token=None):
            seen.append(list(messages))
            return "I do not remember."

        seance.talk(g, "m", input_fn=lambda _: next(answers), say=lambda *_: None, chat_fn=fake_chat)
        self.assertEqual(len(seen), 2)
        self.assertEqual([m["role"] for m in seen[1]], ["system", "user", "assistant", "user"])
        self.assertIn("Remove the legacy script", seen[0][0]["content"])

    def test_talk_survives_a_dead_model(self):
        g = seance.exhume(self.repo)[0]
        answers = iter(["hello?", ""])

        def broken(*a, **k):
            raise OSError("down")

        seance.talk(g, "m", input_fn=lambda _: next(answers), say=lambda *_: None, chat_fn=broken)

    # --- successors and zombies

    def test_successor_follows_a_git_rename(self):
        write(self.repo, "old_engine.py", "".join(f"step_{i}()\n" for i in range(20)))
        commit(self.repo, "Add engine", "2024-02-01T12:00:00")
        run(self.repo, "mv", "old_engine.py", "core_engine.py")
        commit(self.repo, "Rename engine", "2024-06-01T12:00:00")
        g = [x for x in seance.exhume(self.repo) if x.path == "old_engine.py"][0]
        self.assertEqual(seance.find_successor(self.repo, g), ("core_engine.py", 100))

    def test_successor_finds_the_similar_file_added_in_the_same_commit(self):
        body = "".join(f"compute_{i}(value)\n" for i in range(20))
        write(self.repo, "parser_v1.py", body)
        commit(self.repo, "Add parser", "2024-02-01T12:00:00")
        run(self.repo, "rm", "-q", "parser_v1.py")
        write(self.repo, "parsing/parser.py", body.replace("compute_1(", "calc_1(")
              + "".join(f"extra_{i}()\n" for i in range(4)))
        write(self.repo, "parsing/unrelated.py", "".join(f"other_{i}()\n" for i in range(20)))
        commit(self.repo, "Rewrite the parser", "2024-06-01T12:00:00")
        g = [x for x in seance.exhume(self.repo) if x.path == "parser_v1.py"][0]
        path, pct = seance.find_successor(self.repo, g)
        self.assertEqual(path, "parsing/parser.py")
        self.assertTrue(60 <= pct < 100)

    def test_no_successor_when_the_new_files_are_unrelated(self):
        run(self.repo, "rm", "-q", "keep.py")
        write(self.repo, "fresh.py", "".join(f"brand_new_{i}()\n" for i in range(20)))
        commit(self.repo, "Swap files", "2024-06-01T12:00:00")
        g = [x for x in seance.exhume(self.repo) if x.path == "keep.py"][0]
        self.assertIsNone(seance.find_successor(self.repo, g))

    def test_zombies_are_files_that_died_and_came_back(self):
        self.assertEqual(seance.zombies(self.repo), [])
        write(self.repo, "legacy_importer.py", "back\n" * 10)
        commit(self.repo, "Restore it", "2024-04-01T12:00:00")
        run(self.repo, "rm", "-q", "legacy_importer.py")
        commit(self.repo, "Remove again", "2024-05-01T12:00:00")
        write(self.repo, "legacy_importer.py", "back again\n" * 10)
        commit(self.repo, "Restore it again", "2024-06-01T12:00:00")
        self.assertEqual(seance.zombies(self.repo), [("legacy_importer.py", 2)])
        report = seance.coroner(seance.exhume(self.repo) or [self.fake_ghost()], seance.zombies(self.repo))
        self.assertIn("legacy_importer.py (2x)", seance.coroner_text(report))

    def fake_ghost(self):
        g = seance.exhume(self.repo)
        return g[0] if g else seance.Ghost(
            "x", seance.datetime(2024, 1, 1).astimezone(), "a", "m", seance.datetime(2024, 1, 2).astimezone(),
            "a", "m", "c0ffee00", 5, "x", "x")

    # --- last rites

    def stage_deletion_of_a_referenced_file(self):
        write(self.repo, "helpers/plugin_loader.py", "def load():\n    pass\n" * 4)
        write(self.repo, "app.py", "import plugin_loader\n")
        commit(self.repo, "Add plugin loader", "2024-04-01T12:00:00")
        run(self.repo, "rm", "-q", "helpers/plugin_loader.py")

    def test_staged_deletion_finds_what_still_mentions_it(self):
        self.stage_deletion_of_a_referenced_file()
        staged = seance.staged_ghosts(self.repo)
        self.assertEqual([g.path for g in staged], ["helpers/plugin_loader.py"])
        self.assertEqual(staged[0].haunting, [("app.py", 1, "import plugin_loader")])
        self.assertIn("Still haunting 1 place", seance.last_rites_text(staged))

    def test_staged_deletion_with_no_mentions_is_at_peace(self):
        run(self.repo, "rm", "-q", "keep.py")
        staged = seance.staged_ghosts(self.repo)
        self.assertEqual(staged[0].haunting, [])
        self.assertIn("It rests", seance.last_rites_text(staged))

    def test_last_rites_is_silent_with_nothing_staged(self):
        seance.main([self.repo, "--last-rites", "--strict"])

    def test_strict_last_rites_fails_only_when_something_is_haunted(self):
        self.stage_deletion_of_a_referenced_file()
        seance.main([self.repo, "--last-rites", "--no-model"])
        with self.assertRaises(SystemExit) as cm:
            seance.main([self.repo, "--last-rites", "--strict", "--no-model"])
        self.assertEqual(cm.exception.code, 1)

    def test_hook_runs_on_commit_and_warns_without_blocking(self):
        hook = seance.install_hook(self.repo)
        self.assertTrue(os.access(hook, os.X_OK))
        self.stage_deletion_of_a_referenced_file()
        env = {**os.environ, "GIT_AUTHOR_NAME": "Ada", "GIT_AUTHOR_EMAIL": "a@x.io",
               "GIT_COMMITTER_NAME": "Ada", "GIT_COMMITTER_EMAIL": "a@x.io"}
        done = subprocess.run(["git", "-C", self.repo, "commit", "-m", "Drop loader"],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("LAST RITES", done.stdout + done.stderr)
        self.assertIn("app.py:1", done.stdout + done.stderr)

    def test_install_hook_never_overwrites_someone_elses_hook(self):
        hook = os.path.join(self.repo, ".git", "hooks", "pre-commit")
        os.makedirs(os.path.dirname(hook), exist_ok=True)
        with open(hook, "w") as f:
            f.write("#!/bin/sh\necho mine\n")
        with self.assertRaises(RuntimeError):
            seance.install_hook(self.repo)
        with open(hook) as f:
            self.assertIn("echo mine", f.read())

    def test_install_hook_can_be_rerun(self):
        seance.install_hook(self.repo)
        seance.install_hook(self.repo)

    # --- lifespans and the friendly error

    def test_lifespan_chart_has_one_bar_per_ghost_and_escapes_names(self):
        g = seance.exhume(self.repo)[0]
        g.path = "<img src=x>.py"
        svg = seance.lifespan_svg([g])
        self.assertEqual(svg.count("<circle"), 1)
        self.assertNotIn("<img", svg)
        self.assertEqual(seance.lifespan_svg([]), "")
        page = seance.graveyard_html([g], [None], "demo", seance.coroner([g]), lifespans=[g])
        self.assertIn("<svg", page)

    def test_a_folder_that_is_not_a_repo_gets_a_friendly_message(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                seance.main([d, "--no-model"])
            self.assertIn("not a git repository", str(cm.exception.code))

    def test_model_failure_does_not_stop_the_seance(self):
        with mock.patch.object(seance, "chat", side_effect=OSError("down")):
            seance.main([self.repo, "--limit", "1"])

    def test_empty_graveyard_exits(self):
        with tempfile.TemporaryDirectory() as d:
            run(d, "init", "-q")
            write(d, "a", "a\n")
            commit(d, "x", "2024-01-01T12:00:00")
            with self.assertRaises(SystemExit):
                seance.main([d, "--no-model"])


if __name__ == "__main__":
    unittest.main()
