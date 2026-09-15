"""Write rules of the Web API path (AGENTS.md) on a mocked server: a reading status is replaced, never doubled, and never
moved backwards without --force; a plugin's bare tag (keep_bare_tags) and the last reading status are never removed."""
import contextlib, io, unittest
from unittest import mock

from zotero_librarian import taxonomy as tx, zapi

ENV = {"ZOTERO_API_KEY": "AbCdEfGhIjKlMnOpQrStUvWx", "ZOTERO_LIBRARY_ID": "1"}
BARE = sorted(tx.KEEP_BARE_TAGS)[0] if tx.KEEP_BARE_TAGS else "notion"


class TagRules(unittest.TestCase):
    def setUp(self):
        self.item = {"version": 7, "data": {"title": "T", "tags": [{"tag": "status:read", "type": 0}, {"tag": BARE, "type": 0}, {"tag": "method:vla", "type": 0}]}}
        self.written = []
        for p in (mock.patch.object(zapi, "env_or_die", return_value=ENV), mock.patch.object(zapi, "get_item", return_value=(200, self.item)),
                  mock.patch.object(zapi, "patch", side_effect=lambda env, key, version, fields: self.written.append(fields)), mock.patch.object(zapi, "log")):
            p.start(); self.addCleanup(p.stop)

    def written_tags(self): return [t["tag"] for t in self.written[-1]["tags"]]

    def test_a_status_replaces_the_reading_status_and_moves_backwards_only_with_force(self):
        with contextlib.redirect_stdout(io.StringIO()):                     # check_tags prints its warnings
            with self.assertRaises(RuntimeError): zapi.add_tags("K", ["status:to-read"])           # read -> to-read is backwards
            self.assertEqual(self.written, [])
            self.assertEqual(zapi.add_tags("K", ["status:to-read"], force=True), "ok +status:to-read (−status:read)")
            self.assertEqual(self.written_tags(), [BARE, "method:vla", "status:to-read"])
            zapi.add_tags("K", ["embod:dex-hand"]); self.assertEqual(self.written_tags(), ["status:read", BARE, "method:vla", "embod:dex-hand"])
            self.assertEqual(zapi.add_tags("K", ["method:vla"]), "(already tagged)")

    def test_plugin_tags_and_the_last_status_are_never_removed(self):
        if not tx.KEEP_BARE_TAGS: self.skipTest("no keep_bare_tags in taxonomy.toml")
        with self.assertRaises(RuntimeError): zapi.remove_tags("K", [BARE])
        with self.assertRaises(RuntimeError): zapi.remove_tags("K", ["status:read"])
        self.assertEqual(self.written, [])
        self.assertEqual(zapi.remove_tags("K", ["method:vla"]), "ok −method:vla"); self.assertEqual(self.written_tags(), ["status:read", BARE])


if __name__ == "__main__": unittest.main()
