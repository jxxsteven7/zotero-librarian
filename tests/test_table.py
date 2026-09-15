"""The report table: markdown for an agent (piped), aligned and cut to the terminal for a human."""
import os, unittest
from unittest import mock

from zotero_librarian import table

ROWS = [["`ABCD1234`", "A very long paper title that will not fit in a narrow terminal at all", "Dex-Manipulation", "method:vla, embod:single-arm", "yes", "sync ok. —"]]
COLS = ["key", "title", "collection", "tags", "PDF", "notes"]


class Table(unittest.TestCase):
    def test_markdown_when_piped(self):
        with mock.patch.object(table, "HUMAN", False):
            out = table.render(COLS, ROWS)
        self.assertEqual(out.split("\n")[1], "|---|---|---|---|---|---|"); self.assertIn("| `ABCD1234` | A very long", out)

    def test_aligned_and_cut_for_a_terminal(self):
        with mock.patch.object(table, "HUMAN", True), mock.patch.dict(os.environ, {"COLUMNS": "100", "LINES": "40"}):
            out = table.render(COLS, ROWS)
        lines = out.split("\n")
        self.assertEqual(len(lines), 3); self.assertNotIn("`", out); self.assertNotIn("|", out)
        self.assertTrue(all(len(l) <= 100 for l in lines), [len(l) for l in lines]); self.assertIn("…", lines[2])


if __name__ == "__main__": unittest.main()
