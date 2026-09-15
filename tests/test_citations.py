"""refs --library: Semantic Scholar answers are cached in cache/s2/, and only a request that actually went out is followed
by the rate-limit pause (no network here: the lookup is mocked)."""
import contextlib, io, os, shutil, tempfile, unittest
from unittest import mock

from zotero_librarian import citations, localdb

LIB = [dict(key="K1", title="[2023] [CoRL] One", url="https://arxiv.org/abs/2301.00001", doi="", extra=""),
       dict(key="K2", title="[2024] [RSS] Two", url="", doi="10.48550/arXiv.2401.00002", extra="")]
ANSWER = {"data": [{"citedPaper": {"title": "One", "externalIds": {"ArXiv": "2301.00001"}}}]}


class LibraryGraph(unittest.TestCase):
    def test_no_pause_after_a_cache_hit(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.object(citations, "S2DIR", d), mock.patch.object(citations, "CACHE", d), mock.patch.object(localdb, "load", return_value=LIB), \
             mock.patch.object(citations, "_get", return_value=ANSWER) as get, mock.patch("time.sleep") as sleep, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(citations.library(top=5), [("K2", "K1")]); self.assertEqual(sleep.call_count, 2)     # two papers, two requests
            for path, params in (call.args for call in get.call_args_list):                                        # now cached: no pause on the second run
                with open(citations._cache_path(path, params), "w", encoding="utf-8") as f: f.write("{}")
            citations.library(top=5); self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__": unittest.main()
