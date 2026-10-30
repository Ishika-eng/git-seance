import os
import subprocess
import tempfile
import unittest
from unittest import mock

import seance


def run(repo, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Ada", "GIT_AUTHOR_EMAIL": "a@x.io",
           "GIT_COMMITTER_NAME": "Ada", "GIT_COMMITTER_EMAIL": "a@x.io"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=env)


def commit(repo, msg, date):
    run(repo, "add", "-A")
    run(repo, "commit", "-m", msg, date=date)


class SeanceTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.repo = self.dir.name
        run(self.repo, "init", "-q")
        body = "".join(f"line {i}\n" for i in range(10)) + "print('bye')\n"
        with open(os.path.join(self.repo, "old.py"), "w") as f:
            f.write(body)
        with open(os.path.join(self.repo, "blob.bin"), "wb") as f:
            f.write(b"\0\1\2" * 50)
        with open(os.path.join(self.repo, "keep.py"), "w") as f:
            f.write("x\n" * 10)
        commit(self.repo, "Add old things", "2024-01-01T12:00:00")
        run(self.repo, "rm", "-q", "old.py", "blob.bin")
        commit(self.repo, "Remove the legacy script", "2024-03-01T12:00:00")

    def tearDown(self):
        self.dir.cleanup()

    def test_finds_deleted_text_file_with_facts(self):
        ghosts = seance.exhume(self.repo)
        self.assertEqual([g.path for g in ghosts], ["old.py"])
        g = ghosts[0]
        self.assertEqual(g.born_by, "Ada")
        self.assertEqual(g.died_msg, "Remove the legacy script")
        self.assertEqual(g.days_lived, 60)
        self.assertEqual(g.last_words, "print('bye')")
        self.assertEqual(g.lines, 11)

    def test_binary_and_living_files_are_skipped(self):
        paths = [g.path for g in seance.exhume(self.repo)]
        self.assertNotIn("blob.bin", paths)
        self.assertNotIn("keep.py", paths)

    def test_prompt_contains_only_git_facts(self):
        prompt = seance.build_prompt(seance.exhume(self.repo)[0])
        self.assertIn("Remove the legacy script", prompt)
        self.assertIn("Lived 60 days", prompt)

    def test_ofrenda_includes_whisper_and_headstone(self):
        ghosts = seance.exhume(self.repo)
        text = seance.ofrenda(ghosts, ["I remember."], "demo")
        self.assertIn("## old.py", text)
        self.assertIn("> I remember.", text)

    def test_model_failure_does_not_stop_the_seance(self):
        with mock.patch.object(seance, "ask_model", side_effect=OSError("down")):
            seance.main([self.repo, "--limit", "1"])

    def test_empty_graveyard_exits(self):
        with tempfile.TemporaryDirectory() as d:
            run(d, "init", "-q")
            open(os.path.join(d, "a"), "w").write("a\n")
            commit(d, "x", "2024-01-01T12:00:00")
            with self.assertRaises(SystemExit):
                seance.main([d, "--no-model"])


if __name__ == "__main__":
    unittest.main()
