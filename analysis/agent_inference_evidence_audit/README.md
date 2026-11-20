# 单 Agent 推理参数证据审计

本目录记录 10T Synthetic MoE 单 Agent 推理模型的输入参数证据、推导过程和不确定性。所有来源截至 2026-11-20。

- `parameter_ledger.csv`：52 项参数逐项台账。
- `audit_report.md`：研究报告、统计口径、公式、限制与结论。
- `sensitivity_results.csv`：当前模型的关键敏感性输出。
- `scenario_gpu_hours.csv`：由独立审计脚本生成的三种情景结果（CI Artifact）。
- 主独立配置：`config/agent_inference_evidence.json`。

证据分类：
- A：公开测量/厂商规格。
- B：根据公开数据与公式推导。
- C：情景假设。

重要原则：
1. Agent workdays ≠ LLM active time ≠ GPU-hours。
2. Anthropic 平台并发 ≠ 推理活跃序列数。
3. AL4 工作覆盖率 ≠ Token/GPU 份额。
4. API list-price spend ≠ 实际硬件成本，也不能唯一反推 Token。
5. 10T MoE 是合成架构，不是已发布模型。
6. GPU-hours 是工作量；部署 GPU 数是模型常驻容量，两者必须分别报告。

本次只允许修改独立推理模块、模型配置、GPU规格配置及本目录文件；不得修改团队主流程和非推理资源计算。
