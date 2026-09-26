import unittest
from store import ALLOWED_STAGES, CandidateError, CandidateStore


class TestStages(unittest.TestCase):
    def test_create_starts_applied(self):
        s = CandidateStore()
        a = s.create("Priya Shah")
        self.assertEqual(a["stage"], "applied")

    def test_set_stage(self):
        s = CandidateStore()
        a = s.create("Jordan Lee")
        b = s.set_stage(a["id"], "interview")
        self.assertEqual(b["stage"], "interview")

    def test_unknown_stage(self):
        s = CandidateStore()
        a = s.create("Sam Okoye")
        with self.assertRaises(CandidateError):
            s.set_stage(a["id"], "ghost")

    def test_closed_list(self):
        self.assertEqual(set(ALLOWED_STAGES), set(['applied', 'screen', 'interview', 'offer', 'hired', 'rejected']))


if __name__ == "__main__":
    unittest.main()
