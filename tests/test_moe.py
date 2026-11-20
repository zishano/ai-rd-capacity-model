import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from inference.moe import calculate,architecture_stats,_read,DEFAULT_MODEL
class MoEModelTest(unittest.TestCase):
 def test_parameter_accounting(self):
  z=architecture_stats(_read(DEFAULT_MODEL))
  self.assertLess(abs(z["total_parameter_error_fraction"]),0.005)
  self.assertLess(z["active_parameters_derived"],z["total_parameters_derived"])
 def test_hardware_deployment(self):
  w={"input_tokens":633600,"output_tokens":46080,"prefix_cache_hit_rate":0.55,"context_tokens":16384,"peak_sequences":1}
  for hw in ("H100_SXM","H200_SXM","B200_SXM","GB300_NVL72"):
   z=calculate(w,hw); self.assertGreater(z["deployment_gpus_per_replica"],0); self.assertGreater(z["infer_gpu_h"],0)
   self.assertIn(z["prefill"]["bottleneck"],("compute","hbm","communication"))
 def test_cache_reduces_prefill(self):
  w={"input_tokens":633600,"output_tokens":46080,"context_tokens":16384,"peak_sequences":1}
  a=calculate({**w,"prefix_cache_hit_rate":0}); b=calculate({**w,"prefix_cache_hit_rate":0.5})
  self.assertLess(b["prefill"]["service_seconds"],a["prefill"]["service_seconds"])
  self.assertEqual(a["decode"]["service_seconds"],b["decode"]["service_seconds"])
if __name__=="__main__": unittest.main()
