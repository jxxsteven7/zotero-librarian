"""Title format `[YYYY-MMDD] [Venue] Title`, Short Title and de-duplication normalization."""
import unittest

from zotero_librarian import titles


class Titles(unittest.TestCase):
    def test_date_is_written_as_far_as_it_is_known(self):
        self.assertEqual(titles.fmt_date("2025-05-06"), "2025-0506"); self.assertEqual(titles.fmt_date("2008-11-00"), "2008-11")
        self.assertEqual(titles.fmt_date("1987"), "1987"); self.assertEqual(titles.fmt_date(""), "????")
        self.assertEqual(titles.fmt_date("2019-6-9"), "2019-0609"); self.assertEqual(titles.fmt_date("2019/6/9"), "2019-0609")   # HighWire citation_date, unpadded
        self.assertEqual(titles.fmt_date("2019-00-00"), "2019"); self.assertEqual(titles.fmt_date("June 2019"), "????")

    def test_an_existing_prefix_is_kept_unless_it_is_a_placeholder(self):
        """tidy on an item that already carries [date] [venue]: the date only gains precision, the venue only fills ???? / arXiv,
        a nickname in the venue slot survives."""
        self.assertEqual(titles.merge_prefix("2023-0512", "RSS", "2024-0301", "T-RO"), ("2023-0512", "RSS"))
        self.assertEqual(titles.merge_prefix("2023-05", "arXiv", "2023-0512", "CoRL"), ("2023-0512", "CoRL"))
        self.assertEqual(titles.merge_prefix("2023", "ALOHA/ACT", "2023-0423", "RSS"), ("2023-0423", "ALOHA/ACT"))
        self.assertEqual(titles.merge_prefix("2023-0512", "????", "????", "arXiv"), ("2023-0512", "????"))
        self.assertEqual(titles.merge_prefix(None, None, "2024-0301", "T-RO"), ("2024-0301", "T-RO"))

    def test_prefix_round_trip(self):
        t = titles.make_title({"title": "Title: sub", "date": "2025-05-06", "venue": "CoRL"})
        self.assertEqual(t, "[2025-0506] [CoRL] Title: sub"); self.assertEqual(titles.split_prefix(t), ("2025-0506", "CoRL", "Title: sub"))
        self.assertEqual(titles.split_prefix("Plain"), (None, None, "Plain")); self.assertEqual(titles.strip_prefix("[2025-0506] [CoRL] [ALOHA] X"), "X")

    def test_short_title_prefers_nickname_then_the_part_before_the_colon(self):
        self.assertEqual(titles.short_title("[2025-0506] [CoRL] [ALOHA/ACT] Learning fine-grained: bimanual"), "ALOHA/ACT")
        self.assertEqual(titles.short_title("[2025-0506] [CoRL] Foo: bar baz"), "Foo"); self.assertEqual(titles.short_title("No colon here ✅"), "No colon here")

    def test_normalization_and_latex(self):
        self.assertEqual(titles.norm_title("[2025] [arXiv] Hello, World!"), "helloworld"); self.assertEqual(titles.clean_title("$\\pi_0$: A Vision"), "pi0: A Vision")

    def test_pi_model_names_are_ascii(self):
        # Physical Intelligence's models: π0.5 -> pi0.5 (searchable); a π that is not followed by a digit is left alone
        self.assertEqual(titles.clean_title("π0.5: a Vision-Language-Action Model"), "pi0.5: a Vision-Language-Action Model")
        self.assertEqual(titles.clean_title("$π_0$: A Flow Model"), "pi0: A Flow Model"); self.assertEqual(titles.ascii_pi("π₀.₆ learns"), "pi0.6 learns")
        self.assertEqual(titles.ascii_pi("Learning π-shaped grasps with 2π rotations"), "Learning π-shaped grasps with 2π rotations")
        self.assertEqual(titles.norm_title("[2025-0422] [arXiv] π0.5: a Model"), titles.norm_title("pi0.5: a Model"))   # the same paper for the duplicate check
        self.assertEqual(titles.short_title("[2025-0422] [arXiv] pi0.5: a Model"), "pi0.5")


if __name__ == "__main__": unittest.main()
