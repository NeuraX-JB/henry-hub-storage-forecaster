"""Regression checks for release cutoffs, chronology, immutable issue and scoring."""
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
import json

import model
import refresh


class WeekAndReleaseTests(TestCase):
    def test_five_distinct_prior_fridays(self):
        for target in (date(2008, 2, 29), date(2021,1,1), date(2026,11,20)):
            weeks = [model.analog_week(target, i) for i in range(1,6)]
            self.assertEqual(len(set(weeks)), 5)
            self.assertTrue(all(w.weekday() == 4 and w < target for w in weeks))
            self.assertTrue(all(abs((target-w).days-365.25*i) < 4.5 for i,w in enumerate(weeks,1)))

    def test_thanksgiving_cutoff_and_required_prior_stock(self):
        t = date(2026,11,20)
        cut = refresh.deadline(date(2026,11,25), "<tr><td>Wednesday, November 25, 2026</td><td>Thanksgiving</td><td>12:00 p.m.</td></tr>")
        self.assertEqual(refresh.timestamp(cut), "2026-11-25T17:00:00Z")
        base = t - model.WEEK
        for when, valid in [(datetime(2026,11,20,14,59,tzinfo=timezone.utc), False),(cut-timedelta(seconds=1), True),(cut, False)]:
            self.assertEqual(refresh.eligible(t,cut,when,{base:3882},base,True),valid)
        self.assertFalse(refresh.eligible(t,cut,cut-timedelta(minutes=1),{t:3000},base,True))
        self.assertFalse(refresh.eligible(t,cut,cut-timedelta(minutes=1),{base:3000},base,False))

    def test_current_bulletin_can_fill_one_lagged_archive_week(self):
        base, end = date(2026,11,6), date(2026,11,13)
        report = {"week":end, "stock":3882, "previous_stock":3862, "change":20}
        stocks, changes = {base:3862}, {}
        refresh.reconcile_report(stocks, changes, report)
        self.assertEqual((stocks[end],changes[end]),(3882,20))
        for mismatch in ({base:100}, {base-model.WEEK:3862}, {end+model.WEEK:3882}):
            with self.assertRaises(ValueError):
                refresh.reconcile_report(mismatch,{},report)

    def test_frozen_issue_never_changes_and_publication_must_match(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/"2026-11-20.json"
            issue = {"issued_at":"2026-11-22T11:00:00Z","scheduled_release":"2026-11-25T17:00:00Z"}
            original = refresh.json_bytes(issue)
            refresh.save_once(path, original); refresh.save_once(path, b"x")
            self.assertEqual(path.read_bytes(), original)
            actual = refresh.parse_stamp(issue["scheduled_release"])
            dep = [{"created_at":"2026-11-22T11:01:00Z","sha":"abc","id":1,"statuses_url":"statuses"}]
            status = [{"created_at":"2026-11-22T11:02:00Z","state":"success"}]
            for content, verified in [(original, True),(b"changed", False)]:
                with patch.object(refresh,"read_url",side_effect=[json.dumps(dep).encode(),json.dumps(status).encode(),content]):
                    self.assertEqual(bool(refresh.verified_publication(path,issue,actual)),verified)
            status[0]["created_at"] = issue["scheduled_release"]
            with patch.object(refresh,"read_url",side_effect=[json.dumps(dep).encode(),json.dumps(status).encode()]):
                self.assertIsNone(refresh.verified_publication(path,issue,actual))

    def test_current_and_future_outcomes_excluded(self):
        start = date(2010,1,1)
        weeks = [start+i*model.WEEK for i in range(650)]
        weather = {w: (float((i*17)%220),float((i*11)%90)) for i,w in enumerate(weeks)}
        actual = {w: float((i*31)%130-75) for i,w in enumerate(weeks)}
        target = weeks[625]
        replay, estimate = model.walk_forward(actual,weather,target)
        self.assertLess(estimate["train_through"],target.isoformat())
        self.assertLess(estimate["low"],estimate["forecast"])
        self.assertGreater(estimate["high"],estimate["forecast"])
        for i in range(625,650):
            actual[weeks[i]] += 9999
        replay2, estimate2 = model.walk_forward(actual,weather,target)
        self.assertEqual(estimate, estimate2)
        self.assertEqual(replay,replay2)
        self.assertTrue(all(r["train_through"] < r["week"] for r in replay))
        self.assertEqual(model.performance([])["mae"], None)


if __name__ == "__main__":
    main()
