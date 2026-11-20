import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inference.moe import calculate, architecture_stats, _read, DEFAULT_MODEL

class MoEModelTest(unittest.TestCase):
    def setUp(self):
        self.workload={
            "input_tokens":633600,
            "output_tokens":46080,
            "prefix_cache_hit_rate":0.55,
            "context_tokens":16384,
            "peak_sequences":1,
            "decode_batch_sequences":1
        }

    def test_parameter_accounting(self):
        z=architecture_stats(_read(DEFAULT_MODEL))
        self.assertAlmostEqual(z["total_parameters_derived"],1e13,delta=1e9)
        self.assertAlmostEqual(z["active_parameters_derived"]/1e9,32.82374656,places=5)
        self.assertLess(z["active_parameters_derived"],z["total_parameters_derived"])

    def test_hardware_profiles_are_feasible(self):
        for hw in ("H100_SXM","H200_SXM","B200_SXM","GB300_NVL72"):
            z=calculate(self.workload,hw)
            self.assertGreater(z["deployment_gpus_per_replica"],0)
            self.assertGreater(z["infer_gpu_h"],0)
            self.assertIn(z["prefill"]["bottleneck"],("compute","hbm","communication"))

    def test_cache_reduces_prefill_not_decode(self):
        a=calculate({**self.workload,"prefix_cache_hit_rate":0})
        b=calculate({**self.workload,"prefix_cache_hit_rate":0.5})
        self.assertLess(b["prefill"]["service_seconds"],a["prefill"]["service_seconds"])
        self.assertEqual(a["decode"]["service_seconds"],b["decode"]["service_seconds"])

    def test_tensor_parallel_override(self):
        a=calculate(self.workload,"H100_SXM",tensor_parallel_size=4)
        b=calculate(self.workload,"H100_SXM",tensor_parallel_size=8)
        self.assertNotEqual(a["deployment_gpus_per_replica"],b["deployment_gpus_per_replica"])

if __name__=="__main__":
    unittest.main()
