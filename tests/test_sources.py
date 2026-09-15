"""Metadata sources on canned responses (no network): the arXiv API's error entry vs a real title containing "Error",
Crossref dates, and the duplicate check against how the tool itself stores an arXiv id."""
import unittest
from unittest import mock

from zotero_librarian import fetch, sources

ATOM = '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">{}</feed>'
ERROR = ATOM.format('<entry><id>http://arxiv.org/api/errors#incorrect_id_format_for_2112.05251x</id><title>Error</title><summary>incorrect id format</summary></entry>')
PAPER = ATOM.format('<entry><id>http://arxiv.org/abs/2112.05251v2</id><title>Error-Aware Imitation Learning from Teleoperation Data\n  for Mobile Manipulation</title>'
                    '<summary>We study errors.</summary><published>2021-12-09T18:00:00Z</published><updated>2022-01-05T00:00:00Z</updated>'
                    '<author><name>Josiah Wong</name></author><arxiv:comment>CoRL 2021</arxiv:comment><arxiv:primary_category term="cs.RO"/></entry>')


class ArxivApi(unittest.TestCase):
    def test_a_title_containing_error_is_a_paper_and_the_error_entry_is_not(self):
        with mock.patch.object(sources, "get_text", return_value=PAPER): m = sources.meta_arxiv_api("2112.05251")
        self.assertEqual((m["title"], m["version"], m["published"], m["category"], m["comment"]),
                         ("Error-Aware Imitation Learning from Teleoperation Data for Mobile Manipulation", 2, "2021-12-09", "cs.RO", "CoRL 2021"))
        with mock.patch.object(sources, "get_text", return_value=ERROR), self.assertRaises(RuntimeError): sources.meta_arxiv_api("2112.05251x")


class Crossref(unittest.TestCase):
    def test_date_parts_may_be_empty(self):
        self.assertEqual(sources.cr_date({"date-parts": [[2024, 3, 1]]}), "2024-03-01"); self.assertEqual(sources.cr_date({"date-parts": [[2024]]}), "2024")
        self.assertEqual(sources.cr_date({"date-parts": []}), ""); self.assertEqual(sources.cr_date(None), "")


class Duplicates(unittest.TestCase):
    def test_the_arxiv_id_is_found_in_the_doi_the_tool_writes(self):
        """URL = project page, DOI = 10.48550/arXiv.<id>, title edited since: the id in the DOI (or in `extra`) must still match."""
        row = dict(key="K1", title="[2023-0128] [CoRL] A new title", url="https://x.github.io", doi="10.48550/arXiv.2301.12345", extra="arXiv:2301.12345 [cs.RO]")
        with mock.patch.object(fetch, "_LIB", [row]):
            self.assertEqual(fetch.find_duplicate(dict(source="arxiv", id="2301.12345", title="Old title"))["key"], "K1")
            self.assertEqual(fetch.find_duplicate(dict(source="arxiv", id="2301.12345", title="Old title", doi=""))["key"], "K1")
            for other in ("2301.1234", "301.12345", "2301.12346"):                      # a prefix / suffix of the id is not the id
                self.assertIsNone(fetch.find_duplicate(dict(source="arxiv", id=other, title="Other")), other)


if __name__ == "__main__": unittest.main()
