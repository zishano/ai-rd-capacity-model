import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inference.moe import architecture_stats,_read
class MoEActiveScenarioTest(unittest.TestCase):
 def test_total_params_fixed_active_params_ordered(self):
  names=["moe_10t_low_active.json","moe_10t.json","moe_10t_high_active.json"]
  stats=[architecture_stats(_read(ROOT/"config/models"/n)) for n in names]
  for z in stats:self.assertAlmostEqual(z["total_parameters_derived"],1e13,delta=1e9)
  self.assertLess(stats[0]["active_parameters_derived"],stats[1]["active_parameters_derived"])
  self.assertLess(stats[1]["active_parameters_derived"],stats[2]["active_parameters_derived"])
if __name__=="__main__":unittest.main()
