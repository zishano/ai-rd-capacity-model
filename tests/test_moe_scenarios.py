import sys,unittest,csv,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inference.moe import architecture_stats,_read
class MoEActiveScenarioTest(unittest.TestCase):
 def test_total_params_fixed_active_params_ordered(self):
  names=["moe_40t_low_active.json","moe_40t.json","moe_40t_high_active.json"]
  stats=[architecture_stats(_read(ROOT/"config/models"/n)) for n in names]
  for z in stats:self.assertEqual(z["total_parameters_derived"],39_998_895_001_600)
  self.assertLess(stats[0]["active_parameters_derived"],stats[1]["active_parameters_derived"])
  self.assertLess(stats[1]["active_parameters_derived"],stats[2]["active_parameters_derived"])
 def test_hardware_sweep_writes_twelve_rows(self):
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/"sweep.csv"
   subprocess.run([sys.executable,str(ROOT/"scripts/moe_hardware_sweep.py"),"--output",str(out)],cwd=ROOT,check=True,capture_output=True,text=True)
   with out.open(encoding="utf-8",newline="") as f: rows=list(csv.DictReader(f))
   self.assertEqual(len(rows),12)
if __name__=="__main__":unittest.main()
