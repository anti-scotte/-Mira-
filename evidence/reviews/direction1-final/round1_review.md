# Review report

```json
{
  "schema": "agent_teams.review_submission.v2",
  "summary": "两项指派修复均已确认落实，无新增关键问题；仅剩 1 处不影响数值的措辞问题。\n- 「DFT 凸包距离」定义已在证据正文与三份 CSV 之间统一为原始凸包列，命中判据同为该列 ≤ 0，双口径矛盾消除。\n- 实算 F1 现登记为 0.268762，四项计数求和等于全量 215488，代入登记公式逐位复现，与模型卡绝对差 0.666，已如实判为未通过。\n- 直接回归未发现：S 20/20、C 20/20、共享 18、独有各 2、差集恒等式仍为 0=0，标签与距离逐行一致。\n- 尚存措辞问题：旧摘要状态仍写「原参考能公式有误」，与 0.20473 恰为本轮公式输出的复算结果相反。",
  "target_artifacts": [
    "shared/c_hits_detail.csv",
    "shared/divergence_4rows.csv",
    "shared/recheck_evidence.json",
    "shared/s_hits_detail.csv"
  ],
  "findings": [],
  "observations": [
    {
      "observation_id": "observation-1",
      "title": "旧摘要归因仍写「原参考能公式有误」",
      "priority": "P2",
      "reason": "证据 /previous_summary_f1/status 仍为「原参考能公式有误，已由修订复算取代」。上一轮复算显示 0.20473 恰是本轮登记公式（冠军预测形成能与原始凸包列之差）的输出，因此「原公式有误」这一归因与事实相反。该字段属旧值归档说明，不影响本轮 0.268762、命中数与差集恒等式；报告负责人改写旧摘要段时应改为「旧值对应修订前登记口径，新口径的复算结果见 /f1_check」，不要沿用「原公式有误」。",
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ]
    },
    {
      "observation_id": "observation-2",
      "title": "运行日志与归档件仍保留旧脚本输出",
      "priority": "P2",
      "reason": "/execution/stdout 仍是旧脚本的 F1=0.9346141647，/execution/archived_result 仍指向与旧件字节相同的 513 B 文件，/field_comparison 15 项「一致」是旧件对新件的同文件对照。三者与修订后的 passed=false 并存不矛盾，但建议在 /execution 处注明「该日志来自修订前脚本，仅作历史对照；现行 F1 以 /f1_check 的独立复算为准」，避免读者把 0.9346 当成现行结论。",
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ]
    },
    {
      "observation_id": "observation-3",
      "title": "本轮未在原始 gz 上做第二遍全量复算",
      "priority": "P2",
      "reason": "复核在可访问范围内只验证了 0.268762 与登记判别式、混淆矩阵三者自洽（四项求和 215488、F1 逐位一致、10 条样例逐行相符），未重新读取 64706751.gz 与 70836372.gz。原始压缩输入上的独立全量重算仍待另一位真人队员完成，这是本轮核验的边界，不构成对修复的否定。",
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ]
    }
  ],
  "checks": [
    {
      "finding_id": "207e2f7f-5dda-46ee-b7b8-1f1f77b294a3",
      "result": "satisfied",
      "reason": "/top20/rule、/top20/reference_distance_definition 与 /f1_check/dft_reference_formula 已统一把 dft_hull_distance_eV_per_atom 定义为原始 e_above_hull_mp2020_corrected_ppd_mp 并注明未做 e_form−hull 相减；F1 阳性参考条件同为该列 ≤ 0。三份 CSV 该列与 /top20/rows、/top20/divergence_rows 逐行相同，is_hit 与「距离 ≤ 0」逐行一致（0 处矛盾，包括 wbm-4-26594 的 −0.008852）。从 CSV 重算得 S 20/20、C 20/20、共享 18、仅 S 两个（wbm-1-38115、wbm-1-36714）、仅 C 两个（wbm-3-52495、wbm-2-35012），差集恒等式 0=0；四个独有候选距离 −0.347437、−0.31012、−0.309271、−0.30364 与 /archived_result_data/unique_distances 一致。",
      "artifact_refs": [
        "shared/recheck_evidence.json",
        "shared/s_hits_detail.csv",
        "shared/c_hits_detail.csv",
        "shared/divergence_4rows.csv"
      ],
      "task_result_refs": []
    },
    {
      "finding_id": "c2ea8747-2add-43e0-b5f8-1dfc98da2b0b",
      "result": "satisfied",
      "reason": "修订后 /f1_check 与 /archived_result_data 登记 n=215488、TP=33149、FP=116、TN=1958、FN=180265，四项求和恰为 215488；以登记公式 2*TP/(2*TP+FP+FN) 复算得 0.26876223756379747，与登记值逐位一致，与模型卡 0.935 绝对差 0.6662377624362026，故 passed=false 与「复算未通过」结论相符。判别式自洽：predicted_distance = pred − hull，阳性判据等价于 pred ≤ hull，因此 TP+FN 等于 hull ≤ 0 的 213414 行、FP+TN 等于 2074 行，上一轮指出的恒等式矛盾已不存在。10 条 sample_rows 的 predicted_distance 逐行等于 pred − dft_reference，hit_label 与「hull ≤ 0」逐一相符。/f1_check/errors 已明写旧值 0.9346141646653677 与登记公式及混淆矩阵不相容。范围限制：本轮未重读原始 gz 做第二遍全量复算，只验证了数值与登记公式、混淆矩阵三者自洽。",
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ],
      "task_result_refs": []
    }
  ]
}
```
