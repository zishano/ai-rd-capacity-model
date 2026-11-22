"""Named four-chart forecast preset; concurrency uses its own constrained model."""

PRESET = 'ensemble_uncertainty'
LABEL = '多模型融合与不确定性外推'
NOTE = ('总量：三模型等权预测分布混合；并发：原双门槛 + 28 天分块 Bootstrap。'
        '区间未经长期覆盖率校准，停滞/回落为独立条件情景')
