import unittest
from store import CandidateError, CandidateStore


class TestCreateList(unittest.TestCase):
    def test_create_and_list(self):
        s = CandidateStore()
        a = s.create("Priya Shah")
        self.assertEqual(a["name"], "Priya Shah")
        self.assertTrue(a["id"].startswith("c_"))
        self.assertEqual(len(s.list()), 1)

    def test_empty_name(self):
        s = CandidateStore()
        with self.assertRaises(CandidateError):
            s.create("  ")

    def test_no_stage_yet(self):
        s = CandidateStore()
        a = s.create("Jordan Lee")
        self.assertNotIn("stage", a)


if __name__ == "__main__":
    unittest.main()
