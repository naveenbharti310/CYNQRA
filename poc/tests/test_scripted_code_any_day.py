"""The code each prepared demo ends with passes its own tests on every day of the week. The Verification Service runs
a task's tests on the day the demo is played, so a test that holds only on some weekdays stops the demo on the others
(Bluedip's app tests once failed every Thursday, Friday and Saturday). The rest of the suite cannot see this: it runs
on whatever day it runs, and the engine starts every test run with a clean environment, on the machine's real date."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from datetime import date

from helpers import POC, TempDir

from cynqra.testrunner import clean_env, python_exe

# Monday 28 December 2026 to Sunday 3 January 2027: every weekday, and a month's and a year's end.
DAYS = ["2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31", "2027-01-01", "2027-01-02", "2027-01-03"]

# `python -m unittest discover`, with date.today() and datetime.now() moved to the day given.
ON_DAY = """\
import datetime as dt, sys, unittest
real_date, real_datetime = dt.date, dt.datetime
shift = real_date.fromisoformat(sys.argv[1]) - real_date.today()

class date(real_date):
    @classmethod
    def today(cls):
        d = real_date.today() + shift
        return cls(d.year, d.month, d.day)

class datetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return real_datetime.now(tz) + shift

    @classmethod
    def today(cls):
        return real_datetime.today() + shift

dt.date, dt.datetime = date, datetime
unittest.main(module=None, argv=["unittest", "discover", "-p", "test_*.py"])
"""


def final_files(scenario: str) -> dict:
    """What the demo's repository holds when its script ends: a later attempt or task replaces an earlier file."""
    folder = POC / "scenarios" / scenario
    files = {}
    for attempts in json.loads((folder / "scenario.json").read_text(encoding="utf-8"))["work"].values():
        for attempt in attempts:
            for name, ref in (attempt.get("files") or {}).items():
                if ref.startswith("@files/") and not name.endswith(".md"):
                    files[name] = folder / ref[1:]
    return files


class EveryDayOfTheWeekTests(unittest.TestCase):
    def test_each_demos_code_passes_its_own_tests_on_every_day_of_the_week(self):
        scenarios = sorted(p.parent.name for p in (POC / "scenarios").glob("*/scenario.json"))
        self.assertTrue(scenarios)
        for scenario in scenarios:
            tmp = TempDir()
            self.addCleanup(tmp.cleanup)
            files = final_files(scenario)
            self.assertTrue([n for n in files if n.startswith("test_")], f"{scenario} writes no tests")
            for name, src in files.items():
                shutil.copy(src, tmp.path / name)
            for day in DAYS:
                with self.subTest(scenario=scenario, day=day):
                    r = subprocess.run([python_exe(), "-c", ON_DAY, day], cwd=tmp.path, env=clean_env(), timeout=120,
                                       stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace")
                    self.assertEqual(r.returncode, 0, f"{scenario} on {date.fromisoformat(day):%A} {day}:\n"
                                                      + r.stderr[-2500:])


if __name__ == "__main__":
    unittest.main()
