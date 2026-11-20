import json,subprocess,sys,tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASELINE={
 "input_m":76.03199999999998,"output_m":5.529599999999999,
 "infer_gpu_h":17.095384615384614,"infer_cards":12,
 "train_gpu_h":1084.8,"eval_gpu_h":108.47999999999999,
 "cpu_peak":217.69066666666666,"ram_peak_tib":1.6299715909090908,
 "ssd_peak_tb":2.04,"durable_tb":37.0877944,"cost_day":10185.781497233638,
 "gpu_installed":84
}

def run(config,out):
 result=subprocess.run([sys.executable,str(ROOT/"model.py"),str(out),"--config",str(config)],cwd=ROOT,capture_output=True,text=True)
 if result.returncode: raise RuntimeError(result.stderr or result.stdout)
 z=json.loads((out/"results.json").read_text(encoding="utf-8"))
 return next(x for x in z["profiles"] if x["level"]=="AL4")

class MoEIntegrationTest(unittest.TestCase):
 def test_dense_default_regression(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td); row=run(ROOT/"config/assumptions.json",p/"dense")
   for k,v in BASELINE.items(): self.assertAlmostEqual(row[k],v,places=8,msg=k)

 def test_moe_only_changes_inference_resource_outputs(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td); cfg=json.loads((ROOT/"config/assumptions.json").read_text(encoding="utf-8"))
   cfg["settings"]["inference_engine"]["value"]="moe_10t"
   cfg["settings"]["moe_hardware"]["value"]="H100_SXM"
   cp=p/"moe.json"; cp.write_text(json.dumps(cfg),encoding="utf-8")
   dense=run(ROOT/"config/assumptions.json",p/"dense")
   moe=run(cp,p/"moe")
   for k in ("input_m","output_m","train_gpu_h","eval_gpu_h","synth_gpu_h","cpu_peak","cpu_h","ram_peak_tib","ram_gib_h","ssd_peak_tb","fs_tb","obj_tb","backup_tb","durable_tb","new_exp_day","attempts_day","review_h_day"):
    self.assertAlmostEqual(dense[k],moe[k],places=8,msg=k)
   self.assertNotEqual(dense["infer_cards"],moe["infer_cards"])
   self.assertGreater(moe["total_parameters"],1e12)
   self.assertGreater(moe["active_parameters"],0)

if __name__=="__main__": unittest.main()
