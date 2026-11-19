import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class BusinessConfigTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.cwd = Path(temp.name)

    def run_cli(self, output, *args, root=ROOT, check=True):
        return subprocess.run(
            [sys.executable, str(root / "model.py"), output, *args],
            cwd=self.cwd, capture_output=True, text=True, check=check,
        )

    def test_reference_year_team_totals_and_replay(self):
        root = self.cwd / "model"
        (root / "config").mkdir(parents=True)
        for module in ROOT.glob("*.py"):
            shutil.copy(module, root)
        base = read_json(ROOT / "config/assumptions.json")
        year = str(base["settings"]["reference_year"]["value"])
        factor = 1.25
        base["settings"]["years"]["value"][year] = factor
        (root / "config/assumptions.json").write_text(json.dumps(base), encoding="utf-8")
        business = dict(researchers=80, avg_online_sessions=97.5, new_experiments_per_day=27.5,
                        gpus_per_training_run=4, hours_per_training_run=2.5)
        (root / "config/business.json").write_text(json.dumps(business), encoding="utf-8")

        self.run_cli("baseline", root=root)
        rows = {p["level"]: p for p in read_json(self.cwd / "baseline/results.json")["profiles"]}
        self.assertAlmostEqual(rows["AL4"]["online"], 97.5)
        self.assertAlmostEqual(rows["AL4"]["new_exp_day"], 27.5)
        self.assertAlmostEqual(rows["AL4"]["train_gpu_h"], rows["AL4"]["attempts_day"] * 4 * 2.5)
        for level in ("AL3", "AL5"):
            for field, key in (("online", "agents"), ("new_exp_day", "head")):
                rate = base["scenarios"][key]["values"][level]
                self.assertAlmostEqual(rows[level][field], 80 * rate * factor)

        (self.cwd / "new.json").write_text(json.dumps({**business, "hours_per_training_run": 5}), encoding="utf-8")
        self.run_cli("changed", "--config", "new.json", root=root)
        changed = next(p for p in read_json(self.cwd / "changed/results.json")["profiles"] if p["level"] == "AL4")
        self.assertAlmostEqual(changed["train_gpu_h"], 2 * rows["AL4"]["train_gpu_h"])
        self.run_cli("replay", "--config", str(self.cwd / "changed/effective_config.json"), root=root)
        self.assertEqual((self.cwd / "changed/forecasts.csv").read_bytes(), (self.cwd / "replay/forecasts.csv").read_bytes())

    def test_malformed_business_input_is_rejected(self):
        business = read_json(ROOT / "config/business.json")
        for field, value in (("researcher", 7), ("researchers", 0), ("gpus_per_training_run", 1.5)):
            with self.subTest(field=field):
                (self.cwd / "bad.json").write_text(json.dumps({**business, field: value}), encoding="utf-8")
                result = self.run_cli("invalid", "--config", "bad.json", check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(field, result.stderr)
                self.assertFalse((self.cwd / "invalid/results.json").exists())
