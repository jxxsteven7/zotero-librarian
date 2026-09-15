"""Web API credentials from .env: a copied .env.example (placeholder text) must not pass as "set" — neither in `zl.py setup`
nor in the Web API commands, which would otherwise fail on a URL built from the placeholder."""
import os, shutil, sqlite3, tempfile, unittest
from unittest import mock

from zotero_librarian import config, zapi

GOOD = {"ZOTERO_API_KEY": "AbCdEfGhIjKlMnOpQrStUvWx", "ZOTERO_LIBRARY_ID": "1234567"}


class Credentials(unittest.TestCase):
    def test_the_example_file_is_recognized_as_unfilled(self):
        env = config.load_env(os.path.join(config.ROOT, ".env.example"))
        self.assertEqual(set(config.cred_problems(env)), {"ZOTERO_API_KEY", "ZOTERO_LIBRARY_ID"})
        self.assertEqual(set(config.cred_problems({})), {"ZOTERO_API_KEY", "ZOTERO_LIBRARY_ID"})

    def test_filled_values_pass_and_a_non_numeric_id_does_not(self):
        self.assertEqual(config.cred_problems(GOOD), {})
        self.assertEqual(list(config.cred_problems(dict(GOOD, ZOTERO_LIBRARY_ID="me@example.org"))), ["ZOTERO_LIBRARY_ID"])

    def test_web_api_commands_stop_before_any_request_and_never_print_the_key(self):
        env = config.load_env(os.path.join(config.ROOT, ".env.example"))
        with mock.patch.object(zapi, "load_env", return_value=env), self.assertRaises(SystemExit) as cm: zapi.env_or_die()
        msg = str(cm.exception)
        self.assertIn("ZOTERO_API_KEY", msg); self.assertIn("ZOTERO_LIBRARY_ID", msg); self.assertNotIn(env["ZOTERO_API_KEY"], msg)
        with mock.patch.object(zapi, "load_env", return_value=GOOD): self.assertEqual(zapi.env_or_die(), GOOD)


class Snapshot(unittest.TestCase):
    def test_a_wal_database_is_copied_once_per_library_state(self):
        """connect_ro copies main file + WAL to a temp dir (Zotero holds the lock); the copy is reused until the writer commits
        again — `add` polls for the item it just saved, so a new commit must produce a new copy."""
        d = tempfile.mkdtemp(); p = os.path.join(d, "zotero.sqlite"); self.addCleanup(shutil.rmtree, d, True)
        w = sqlite3.connect(p); self.addCleanup(w.close); self.addCleanup(config._drop_snapshot, p)
        w.execute("pragma journal_mode=wal"); w.execute("create table items(key text)"); w.execute("insert into items values ('A')"); w.commit()
        self.assertGreater(os.path.getsize(p + "-wal"), 0)
        a, b = config.connect_ro(p), config.connect_ro(p)
        self.assertIs(a, b); self.assertEqual(a.execute("select count(*) from items").fetchone()[0], 1)
        w.execute("insert into items values ('B')"); w.commit()                          # the WAL grows: a new state, a new copy
        c = config.connect_ro(p)
        self.assertIsNot(a, c); self.assertEqual(c.execute("select count(*) from items").fetchone()[0], 2)


if __name__ == "__main__": unittest.main()
