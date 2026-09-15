"""Title format `[YYYY-MMDD] [Venue] Title`, Short Title and de-duplication normalization."""
import unittest

from zotero_librarian import titles


class Titles(unittest.TestCase):
    def test_date_is_written_as_far_as_it_is_known(self):
        self.assertEqual(titles.fmt_date("2025-05-06"), "2025-0506"); self.assertEqual(titles.fmt_date("2008-11-00"), "2008-11")
        self.assertEqual(titles.fmt_date("1987"), "1987"); self.assertEqual(titles.fmt_date(""), "????")

    def test_prefix_round_trip(self):
        t = titles.make_title({"title": "Title: sub", "date": "2025-05-06", "venue": "CoRL"})
        self.assertEqual(t, "[2025-0506] [CoRL] Title: sub"); self.assertEqual(titles.split_prefix(t), ("2025-0506", "CoRL", "Title: sub"))
        self.assertEqual(titles.split_prefix("Plain"), (None, None, "Plain")); self.assertEqual(titles.strip_prefix("[2025-0506] [CoRL] [ALOHA] X"), "X")

    def test_short_title_prefers_nickname_then_the_part_before_the_colon(self):
        self.assertEqual(titles.short_title("[2025-0506] [CoRL] [ALOHA/ACT] Learning fine-grained: bimanual"), "ALOHA/ACT")
        self.assertEqual(titles.short_title("[2025-0506] [CoRL] Foo: bar baz"), "Foo"); self.assertEqual(titles.short_title("No colon here ✅"), "No colon here")

    def test_normalization_and_latex(self):
        self.assertEqual(titles.norm_title("[2025] [arXiv] Hello, World!"), "helloworld"); self.assertEqual(titles.clean_title("$\\pi_0$: A Vision"), "pi0: A Vision")


if __name__ == "__main__": unittest.main()
