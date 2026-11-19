import subprocess
import sys
import unittest
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from notify_indexnow import BASE, changed_urls


class IndexNowTest(unittest.TestCase):
    def test_push_with_an_addition_a_move_and_a_deletion(self):
        def git(*args):
            return subprocess.check_output(["git", *args], text=True).strip()

        def commit(message):
            git("add", "-A")
            git("-c", "user.name=Test", "-c", "user.email=test@example.org",
                "-c", "commit.gpgsign=false", "commit", "-qm", message)

        def article(name, permalink):
            path = Path("ko/nichijou") / (name + ".md")
            path.write_text(f"---\npermalink: {permalink}\nparent_permalink: /ko/nichijou/\n---\nessay\n")

        with TemporaryDirectory() as work, chdir(work):
            git("init", "-q")
            Path("ko/nichijou").mkdir(parents=True)
            article("essay", "/ko/nichijou/old/")
            article("retired", "/ko/nichijou/retired/")
            commit("Baseline")
            before = git("rev-parse", "HEAD")
            article("essay", "/ko/nichijou/new/")
            Path("ko/nichijou/retired.md").unlink()
            commit("Move one article and remove another")
            article("later", "/ko/nichijou/later/")
            commit("Add an article in the same push")

            live = {BASE + path for path in ("/ko/nichijou/", "/ko/nichijou/new/",
                                              "/ko/nichijou/later/", "/en/")}
            expected = {BASE + path for path in ("/ko/nichijou/", "/ko/nichijou/new/",
                                                 "/ko/nichijou/old/", "/ko/nichijou/retired/",
                                                 "/ko/nichijou/later/")}
            self.assertEqual(set(changed_urls(live, before)), expected)
            self.assertEqual(set(changed_urls(live - {BASE + "/ko/nichijou/later/"}, before)), expected)


if __name__ == "__main__":
    unittest.main()
