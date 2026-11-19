import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEST_SOURCE = "https://example.invalid/test-only-report"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_ledger(folder):
    with (folder / "input_sources.csv").open(encoding="utf-8-sig", newline="") as stream:
        return {(r["key"], r["level_or_year"]): r for r in csv.DictReader(stream)}


def run_model(cwd, out, config, overrides=None):
    args = [sys.executable, str(ROOT / "model.py"), out]
    if overrides:
        args.append(overrides)
    subprocess.run([*args, "--config", config], cwd=cwd, check=True, stdout=subprocess.DEVNULL)
    return cwd / out


class ConfigIntegrationTest(unittest.TestCase):
    def test_evidence_updates_and_replay(self):
        config = read_json(ROOT / "config/assumptions.json")
        head = config["scenarios"]["head"]
        head["values"]["AL4"] *= 1.1
        report = {"kind": "A", "scope": "Synthetic fixture", "rationale": "Test measurement", "references": [
            {"title": "Test measurement", "url": TEST_SOURCE, "role": "direct"}
        ]}
        head["evidence"].setdefault("by_level", {})["AL4"] = report
        year = str(config["settings"]["reference_year"]["value"])
        years = config["settings"]["years"]
        years["evidence"].setdefault("by_year", {})[year] = report
        extra_year = str(max(map(int, years["value"])) + 1)

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config_path = cwd / "research.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            first = run_model(cwd, "first", config_path.name)
            baseline = read_ledger(first)
            self.assertEqual(baseline["head", "AL4"]["source_urls"], TEST_SOURCE)
            self.assertNotIn(TEST_SOURCE, baseline["head", "AL3"]["source_urls"])
            profile = next(p for p in read_json(first / "results.json")["profiles"] if p["level"] == "AL4")
            expected = config["fixed"]["people"]["value"] * head["values"]["AL4"] * years["value"][year]
            self.assertAlmostEqual(profile["new_exp_day"], expected)

            overrides = {"AL4": {"head": head["values"]["AL4"]}, "years": {extra_year: 1.0}}
            (cwd / "override.json").write_text(json.dumps(overrides), encoding="utf-8")
            changed = run_model(cwd, "changed", config_path.name, "override.json")
            ledger = read_ledger(changed)
            self.assertEqual(ledger["head", "AL4"]["effective_kind"], "C")
            self.assertEqual(ledger["head", "AL4"]["source_urls"], "")
            self.assertEqual(ledger["head", "AL4"]["config_kind"], "A")
            self.assertEqual(ledger["years", extra_year]["config_value"], "")

            snapshot = changed / "effective_config.json"
            manifest = read_json(changed / "run_manifest.json")
            self.assertEqual(manifest["effective_config_sha256"], hashlib.sha256(snapshot.read_bytes()).hexdigest())
            self.assertEqual(manifest["config_sha256"], hashlib.sha256(config_path.read_bytes()).hexdigest())
            replay = run_model(cwd, "replay", str(snapshot))
            self.assertEqual((changed / "forecasts.csv").read_bytes(), (replay / "forecasts.csv").read_bytes())
            replay_ledger = read_ledger(replay)
            self.assertEqual(replay_ledger["years", year]["source_urls"], TEST_SOURCE)
            self.assertEqual(replay_ledger["head", "AL4"]["source_urls"], "")
