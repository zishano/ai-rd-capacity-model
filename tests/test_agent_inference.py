import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AgentInferenceTest(unittest.TestCase):
    def test_default_example(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "agent_inference.py")],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["task"]["input_tokens"], 1_000_000)
        self.assertEqual(data["task"]["output_tokens"], 200_000)
        self.assertAlmostEqual(data["latency"]["prefill_service_seconds"], 100)
        self.assertAlmostEqual(data["latency"]["decode_service_seconds"], 400)
        self.assertAlmostEqual(data["gpu"]["gpu_hours_per_task"], 0.5555555556)
        self.assertAlmostEqual(data["hbm"]["kv_gb_total"], 3.2768)
        self.assertTrue(data["hbm"]["lower_bound_fits"])

    def test_cache_hit_reduces_prefill_work_not_decode(self):
        config = json.loads((ROOT / "config/agent_inference.json").read_text(encoding="utf-8"))
        config["task"]["input_prefix_cache_hit_rate"] = 0.5
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "agent_inference.py"), "--config", str(path)],
                cwd=ROOT, capture_output=True, text=True, check=True,
            )
        data = json.loads(result.stdout)
        self.assertAlmostEqual(data["latency"]["prefill_service_seconds"], 50)
        self.assertAlmostEqual(data["latency"]["decode_service_seconds"], 400)
        self.assertAlmostEqual(data["gpu"]["gpu_hours_per_task"], 0.5)

    def test_bad_cache_rate_rejected(self):
        config = json.loads((ROOT / "config/agent_inference.json").read_text(encoding="utf-8"))
        config["task"]["input_prefix_cache_hit_rate"] = 1.2
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "agent_inference.py"), "--config", str(path)],
                cwd=ROOT, capture_output=True, text=True,
            )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
