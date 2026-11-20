import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inference.agent_workload import build_daily_workload
from inference.moe import calculate
class AgentWorkloadTest(unittest.TestCase):
 def test_daily_token_formula(self):
  w=build_daily_workload(online_hours=24,inference_duty=.24,input_tokens_per_active_hour=110000,
    output_tokens_per_active_hour=8000,prefix_cache_hit_rate=.55,context_tokens=16384)
  self.assertEqual(w["input_tokens"],633600)
  self.assertEqual(w["output_tokens"],46080)
  self.assertEqual(w["inference_active_hours"],5.76)
 def test_invalid_duty_rejected(self):
  with self.assertRaises(ValueError):
   build_daily_workload(online_hours=24,inference_duty=1.2,input_tokens_per_active_hour=1,
    output_tokens_per_active_hour=1,prefix_cache_hit_rate=.5,context_tokens=1024)
 def test_capacity_lower_bound_exposed(self):
  w={"input_tokens":1000,"output_tokens":100,"prefix_cache_hit_rate":.5,"context_tokens":8192,"peak_sequences":1}
  z=calculate(w,"H100_SXM")
  self.assertGreater(z["hbm_capacity_lower_bound_gpus"],0)
  self.assertGreaterEqual(z["deployment_gpus_per_replica"],z["hbm_capacity_lower_bound_gpus"])
if __name__=="__main__":unittest.main()
