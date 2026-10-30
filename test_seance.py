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
