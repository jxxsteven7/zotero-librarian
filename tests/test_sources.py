"""Metadata sources on canned responses (no network): the arXiv API's error entry vs a real title containing "Error",
Crossref dates, link recognition, a paper indexed nowhere (metadata off the PDF's first page), and the duplicate check
against how the tool itself stores an arXiv id."""
import os, tempfile, unittest
from unittest import mock

from zotero_librarian import fetch, pdf, sources

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


class Links(unittest.TestCase):
    def test_publisher_pages_carry_the_doi_in_the_path(self):
        self.assertEqual(sources.classify_link("https://www.science.org/doi/10.1126/scirobotics.aee1868"), ("doi", "10.1126/scirobotics.aee1868"))
        self.assertEqual(sources.classify_link("https://dl.acm.org/doi/full/10.1145/3712345.3712346?via=x"), ("doi", "10.1145/3712345.3712346"))
        self.assertEqual(sources.classify_link("https://doi.org/10.1109/LRA.2024.1234567"), ("doi", "10.1109/LRA.2024.1234567"))
        self.assertEqual(sources.classify_link("https://hifun-cfu.pages.dev/")[0], "page")
        self.assertEqual(sources.classify_link("https://x.github.io/paper.pdf")[0], "pdf")


FIRST_PAGE = """HiFun: a Hierarchical Framework for Efficient
Functional Dexterous Manipulation Learning
Linyi Huang1 Guowei Huai1 Weibin Liu1
1 HKUST (Guangzhou), China

Abstract: While multi-fingered hands have the potential to provide human-level dexterity,
using them remains difficult. We propose HiFun.
Keywords: Dexterous Manipulation, Reinforcement Learning

1 Introduction
10th Conference on Robot Learning (CoRL) 2026, Seoul, Korea.
"""


class Unindexed(unittest.TestCase):
    """A camera-ready PDF on a project page, on neither arXiv nor Crossref: no model here (ZC_LLM=off), so the first line is
    the title, the abstract comes from the first page, the venue from its statement and the date from the file."""
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        self.tmp.write(b"%PDF-1.7\n1 0 obj << /CreationDate (D:20260602101010+08'00') >> endobj\n%%EOF"); self.tmp.close()

    def tearDown(self): os.remove(self.tmp.name)

    def test_creation_date_from_info_dict_or_xmp(self):
        self.assertEqual(pdf.pdf_creation_date(self.tmp.name), "2026-06-02")
        with open(self.tmp.name, "wb") as f: f.write(b"%PDF-1.7\n<xmp:CreateDate>2025-11-30T10:00:00Z</xmp:CreateDate>\n%%EOF")
        self.assertEqual(pdf.pdf_creation_date(self.tmp.name), "2025-11-30")
        with open(self.tmp.name, "wb") as f: f.write(b"%PDF-1.7\n%%EOF")
        self.assertIsNone(pdf.pdf_creation_date(self.tmp.name))

    def test_metadata_off_the_first_page_without_a_model(self):
        with mock.patch.dict(os.environ, {"ZC_LLM": "off"}):
            m = sources.meta_unindexed(self.tmp.name, FIRST_PAGE, "https://hifun-cfu.pages.dev/assets/hifun.pdf", url="https://hifun-cfu.pages.dev/",
                                       page="<html><h1>HiFun</h1><p>Accepted to CoRL 2026</p></html>")
        self.assertEqual(m["source"], "pdf"); self.assertEqual(m["url"], "https://hifun-cfu.pages.dev/")
        self.assertEqual(m["title"], "HiFun: a Hierarchical Framework for Efficient")           # the first line only: the report says so
        self.assertEqual(m["authors"], []); self.assertIn("no model", m["meta_src"])
        self.assertTrue(m["abstract"].startswith("While multi-fingered") and m["abstract"].endswith("We propose HiFun."))
        self.assertEqual((m["venue"], m["venue_src"]), ("CoRL", "pdf first page"))
        self.assertEqual((m["date"], m["date_src"]), ("2026-06-02", "pdf:file creation date, not the day it appeared !"))
        self.assertEqual((m["item"]["itemType"], m["item"]["date"], m["item"]["url"]), ("conferencePaper", "2026-06-02", "https://hifun-cfu.pages.dev/"))

    def test_the_model_answer_is_used_when_there_is_one(self):
        bib = dict(title="HiFun: a Hierarchical Framework for Efficient Functional Dexterous Manipulation Learning",
                   authors=["Linyi Huang", "Guowei Huai"], abstract="We propose HiFun.", venue="10th Conference on Robot Learning (CoRL) 2026", year="2026")
        with mock.patch("zotero_librarian.llm.bib_fields", return_value=(bib, "qwen-test")):
            m = sources.meta_unindexed(self.tmp.name, FIRST_PAGE, "/tmp/hifun.pdf")
        self.assertEqual(m["title"], bib["title"]); self.assertEqual([a["lastName"] for a in m["authors"]], ["Huang", "Huai"])
        self.assertEqual((m["venue"], m["meta_src"], m["url"]), ("CoRL", "pdf first page, read by qwen-test", "/tmp/hifun.pdf"))
        self.assertEqual(m["item"]["conferenceName"], "10th Conference on Robot Learning (CoRL) 2026")
        no_venue = dict(bib, venue="", year="")
        with mock.patch("zotero_librarian.llm.bib_fields", return_value=(no_venue, "qwen-test")):
            m = sources.meta_unindexed(self.tmp.name, "A title\nAn author\nAbstract: text.\n1 Introduction", "/tmp/x.pdf")
        self.assertEqual((m["venue"], m["item"]["itemType"]), ("????", "preprint")); self.assertIn("!", m["venue_src"])


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
