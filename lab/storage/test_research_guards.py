"""Regression checks for research data integrity and scoring boundaries."""
import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import model
import refresh


class ResearchGuardTests(TestCase):
    def samples(self):
        first = date(2020, 1, 3)
        samples = [(model.Feature(first + i*model.WEEK, 5., float(i % 4), 1., 2., 1.), 6.) for i in range(104)]
        target = model.Feature(first + 105*model.WEEK, 5., 3., 1., 2., 1.)
        return target, samples

    def test_future_sample_not_hidden_by_an_earlier_last_row(self):
        target, samples = self.samples()
        samples[0] = (target, 100.)
        with self.assertRaisesRegex(ValueError, "chronological"):
            model.predict(target, samples, [])

    def test_nonfinite_training_and_invalid_error_history(self):
        target, samples = self.samples()
        with self.assertRaisesRegex(ValueError, "Calibration"):
            model.predict(target, samples, [float("nan")])
        with self.assertRaisesRegex(ValueError, "Calibration"):
            model.predict(target, samples, [-1.])
        samples[0] = (samples[0][0], float("inf"))
        with self.assertRaisesRegex(ValueError, "finite"):
            model.predict(target, samples, [])

    def write_inputs(self, folder, hdd="0", stock="100"):
        files={"storage":"week_ending,working_gas_bcf,change_bcf\n2026-11-13,"+stock+",\n",
               "weather":"week_ending,hdd,cdd,period_start,period_end\n2026-11-20,"+hdd+",0,2026-11-13,2026-11-19\n"}
        sources={}
        for name, body in files.items():
            (folder/(name+".csv")).write_text(body)
            sources[name]={"sha256":hashlib.sha256(body.encode()).hexdigest()}
        (folder/"manifest.json").write_text(json.dumps({"sources":sources}))

    def test_shared_input_hashes_checked_before_modelling(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp); self.write_inputs(folder)
            (folder/"storage.csv").write_text("changed")
            with patch.object(refresh,"DATA",folder), self.assertRaisesRegex(ValueError,"manifest"):
                refresh.load_shared()

    def test_nonphysical_csv_values_rejected_even_with_matching_hash(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for hdd, stock in [("NaN","100"),("-1","100"),("0","-1")]:
                self.write_inputs(folder,hdd,stock)
                with patch.object(refresh,"DATA",folder), self.assertRaisesRegex(ValueError,"finite"):
                    refresh.load_shared()

    def test_eia_nan_stock_rejected(self):
        raw=('"Released: November 19, 2026 at 10:30 a.m."\n"Week Ending November 13, 2026"\n'
             '"Next Release: November 25, 2026"\nRegion,Stock,x,x,Previous,Net change\nTotal,NaN,,,100,20\n').encode()
        with self.assertRaisesRegex(ValueError,"finite"):
            refresh.parse_report(raw)
        with self.assertRaisesRegex(ValueError,"dates"):
            refresh.parse_report(raw.replace(b"NaN",b"120").replace(b"November 13,",b"November 14,"))

    def test_cached_proof_must_match_week_and_publication_window(self):
        issue={"week":"2026-11-20","issued_at":"2026-11-22T11:00:00Z","scheduled_release":"2026-11-25T17:00:00Z"}
        sha="a"*40
        proof={"commit":sha,"published_at":"2026-11-22T11:05:00Z","source":f"https://raw.githubusercontent.com/{refresh.REPO}/{sha}/{refresh.PUBLIC_DIR}/2026-11-20.json"}
        release=refresh.parse_stamp(issue["scheduled_release"])
        self.assertTrue(refresh.publication_matches(proof,issue,release))
        self.assertFalse(refresh.publication_matches({**proof,"published_at":issue["scheduled_release"]},issue,release))
        self.assertFalse(refresh.publication_matches({**proof,"source":proof["source"].replace("11-20","11-13")},issue,release))

    def test_outcome_raw_hash_required(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp); (folder/"ledger").mkdir()
            path=folder/"ledger/2026-11-20-release.json"
            path.write_text(json.dumps({"week":"2026-11-20","raw_file":"ledger/2026-11-20-release.csv","source_sha256":"wrong"}))
            (folder/"ledger/2026-11-20-release.csv").write_text("changed")
            with patch.object(refresh,"HERE",folder), self.assertRaisesRegex(ValueError,"recorded hash"):
                refresh.read_outcome(path,{"week":"2026-11-20"})

    def test_captured_release_reconciles_actual_and_week(self):
        raw=('"Released: November 19, 2026 at 10:30 a.m."\n"Week Ending November 13, 2026"\n'
             '"Next Release: November 25, 2026"\nRegion,Stock,x,x,Previous,Net change\nTotal,120,,,100,20\n').encode()
        with TemporaryDirectory() as tmp:
            folder=Path(tmp); (folder/"ledger").mkdir()
            path=folder/"ledger/2026-11-13-release.json"
            outcome={"week":"2026-11-13","raw_file":"ledger/2026-11-13-release.csv", "actual":20.,
                     "source_sha256":hashlib.sha256(raw).hexdigest(),"reported_at":"2026-11-19T15:30:00Z"}
            path.write_text(json.dumps(outcome))
            (folder/outcome["raw_file"]).write_bytes(raw)
            with patch.object(refresh,"HERE",folder):
                self.assertEqual(refresh.read_outcome(path,{"week":"2026-11-13"}),outcome)
                with self.assertRaisesRegex(ValueError,"different forecast week"):
                    refresh.read_outcome(path,{"week":"2026-11-20"})
                path.write_text(json.dumps({**outcome,"actual":21.}))
                with self.assertRaisesRegex(ValueError,"disagrees"):
                    refresh.read_outcome(path,{"week":"2026-11-13"})

    def test_frozen_replay_results_unchanged(self):
        _, changes, weather=refresh.load_shared()
        state=json.loads((refresh.HERE/"state.json").read_text())
        replay, _=model.walk_forward(changes,weather,date.fromisoformat(state["target"]))
        stats=model.performance(replay)
        self.assertEqual(stats["n"],463)
        for key in ("mae","baseline_mae","coverage"):
            self.assertAlmostEqual(stats[key],state["backtest"][key],places=8)
