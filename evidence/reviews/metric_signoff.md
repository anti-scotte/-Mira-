# Review report

```json
{
  "schema": "agent_teams.review_submission.v2",
  "summary": "核验未通过：2 项关键问题，四行分歧表与命中计数本身可签认。\n- 实算 F1 0.934614 无法用证据自己写的公式在 215488 行原始数据上复现（我复算得 0.268762，八种合理口径最高 0.3018），与模型卡仅差 0.000386、复算通过这一结论目前没有依据。\n- 明细与分歧表的「DFT 凸包距离」实际是原始凸包列本身，而证据正文把它定义成形成能减凸包，同一材料两处定义相差 0.50 到 2.89 eV/atom，40 行无一行相等；命中标签恰好在两种口径下同号，故计数不受影响。\n- 旧摘要 0.2047 的「原公式有误」归因与事实相反：0.20473 正是本轮登记公式的输出，报告负责人不宜据此改写结论。\n- 已核验成立的部分：四行分歧表的 ID、化学式、两种名次与分数、DFT 距离、命中均与冻结全排序和原始压缩输入逐项吻合；S 20/20、C 20/20、共享 18、独有各 2，差集恒等式 0=0；打平成因解释成立，但属候选池机械结果，不能当作策略等价证据。",
  "target_artifacts": [
    "shared/c_hits_detail.csv",
    "shared/divergence_4rows.csv",
    "shared/recheck_evidence.json",
    "shared/s_hits_detail.csv"
  ],
  "findings": [
    {
      "finding_id": "finding-1",
      "title": "实算 F1 无法用登记公式在原始数据上复现",
      "priority": "P0",
      "reason": "证据 /f1_check 与 /archived_result_data 登记 f1=0.9346141646653677、card_f1=0.935、absolute_difference=0.0003858，并据此置 passed=true、写入「方向一脚本复算通过」结论。本轮以证据自述公式（/f1_check/dft_reference_formula = e_form_per_atom_mp2020_corrected − e_above_hull_mp2020_corrected_ppd_mp，/f1_check/predicted_distance_formula = 冠军预测形成能 − 该参考值，阈值 0）在全体系 215488 个独特原型上独立复算，得 TP=33149、FP=116、TN=1958、FN=180265、F1=0.268762，与登记值相差 0.666。另穷举 pred−e_form、pred−hull_mp2020、pred−hull_wbm、pred 直接判定与两套参考列的 8 种组合，F1 全部落在 0.2047~0.3018，无任何组合能得到 0.9346。更关键的是结构性矛盾：按登记公式构造时 TP+FP 恒等于全量 215488，不可能出现登记中的 TN=180220（83.6%）；该混淆矩阵与它自己写的判别式不相容。因此 0.934614 不可复现，「绝对差 <0.02、脚本复算通过」的登记目前缺乏依据。",
      "repair_instruction": "由执行方从 recheck.py 中取出真实使用的参考能公式与判别式，写清 TP/FP/TN/FN 的判定条件，并提供可复算的中间量（至少 10 个样例材料的 pred、参考值、判别量与标签）。据此改写 /f1_check 与 /archived_result_data：若真实 F1 与模型卡 0.935 的绝对差 >0.02，须把 passed 改为 false、结论改为未通过并写明分母与缺口；若公式登记有误，须同时登记正确公式、重算数值与新旧口径差异，不得保留无法复现的 0.934614。",
      "acceptance_criteria": [
        "/f1_check/f1 与 /archived_result_data/f1 可由所登记公式与阈值在 215488 行上逐位复现（容许 1e-9 浮点误差）",
        "/f1_check 登记 TP/FP/TN/FN 的判定条件与公式一致，且 tp+fp+tn+fn=215488",
        "给出至少 10 个样例材料的 pred、DFT 参考值、判别量与标签，可用原始 gz 逐行验证",
        "/f1_check/passed 与 conclusion_status 与重算结果一致：绝对差 >0.02 时不得写作通过"
      ],
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ]
    },
    {
      "finding_id": "finding-2",
      "title": "「DFT 凸包距离」字段与证据给出的定义互相矛盾",
      "priority": "P0",
      "reason": "证据 /top20/rule 与 /f1_check/dft_reference_formula 把参考量定义为 e_form_per_atom_mp2020_corrected − e_above_hull_mp2020_corrected_ppd_mp，但 s_hits_detail.csv、c_hits_detail.csv 与 divergence_4rows.csv 的 dft_hull_distance_eV_per_atom 列实际写入的是未相减的 e_above_hull_mp2020_corrected_ppd_mp 本身（40 行逐行与原始 gz 相同）。按证据正文定义重算，同一材料的参考距离应为 −2.016651（wbm-3-56891）、−2.589612（wbm-2-37232）、−2.885308（wbm-4-26594）等，与登记的 −1.512202、−0.491374、−0.008852 相差 0.50 至 2.89 eV/atom，40 行无一行相等。命中标签两种口径恰好同号（e_form<hull 时 hull 亦 ≤0），故 S 20/20、C 20/20 计数不受影响，但字段语义、判定依据与 F1 定义在同一份证据里互相冲突，读者无法判断命中是按哪个参考量判的。",
      "repair_instruction": "在 recheck_evidence.json 中统一「DFT 参考距离」定义：或把 /top20/rule 与 /f1_check/dft_reference_formula 改写为「命中判据 = e_above_hull_mp2020_corrected_ppd_mp ≤ 0」，或将三份 CSV 的 dft_hull_distance_eV_per_atom 改为 e_form − hull 并按新值重判命中；两者只能取一，并须同步说明 F1 段落使用哪个参考量、命中数在该口径下是否变化。CSV 内数值本身与原始输入一致，无需改数，只需把定义写对并在正文注明列语义。",
      "acceptance_criteria": [
        "/top20/rule、/f1_check/dft_reference_formula 与三份 CSV 的 dft_hull_distance_eV_per_atom 列指同一个量，命名与计算式一致",
        "报告正文明确写出命中判定所用的列名与阈值，并说明 40 行命标签在两种口径下是否同号",
        "改写后 S 20/20、C 20/20 的计数仍能与原始 gz 逐行复算"
      ],
      "artifact_refs": [
        "shared/recheck_evidence.json",
        "shared/s_hits_detail.csv",
        "shared/c_hits_detail.csv",
        "shared/divergence_4rows.csv"
      ]
    }
  ],
  "observations": [
    {
      "observation_id": "observation-1",
      "title": "旧摘要 0.2047 的归因方向与复算结果相反",
      "priority": "P2",
      "reason": "证据 /previous_summary_f1 登记「原参考能公式有误，已由修订复算取代」。但本轮按证据自身登记的公式独立复算得到 0.20473，恰好复现旧摘要的 0.2047，说明 0.2047 与该公式同源，而不是「旧公式有误」。在 F1 问题修复前，报告负责人不宜把「原公式有误」写入最终结论，宜改为「旧值对应本轮登记公式，新值的公式与可复现性待补」。",
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ]
    },
    {
      "observation_id": "observation-2",
      "title": "实跑命令登记与真实执行路径不一致",
      "priority": "P2",
      "reason": "/execution/command_line 写的是 python.exe 第三阶段本地修订\\recheck.py（相对项目根），而 /execution/argv 与 /execution/cwd 显示实际执行的是隔离副本绝对路径。隔离执行的理由（/execution/purpose_of_isolation：原脚本固定写同目录核验结果.json）已说明且可接受，但命令行应改为真实执行的绝对路径，避免读者误判审计对象。",
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ]
    },
    {
      "observation_id": "observation-3",
      "title": "归档件与旧件字节相同，逐字段比对无法证明公式被修订",
      "priority": "P2",
      "reason": "本次归档 核验结果_本次实跑.json 与旧件备份均为 513 B、同为 07babb5c…，/field_comparison 15 项全部一致、byte_equal=true。逐字段比对本身如实完成，但两次结果同源，只能证明脚本被原样再跑一遍并写回旧值，不能证明公式已修订；与 F1 不可复现叠加后，反而是保留了一份不可复现数值的旁证。",
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ]
    },
    {
      "observation_id": "observation-4",
      "title": "Windows 原件路径无法在本运行时独立验证",
      "priority": "P2",
      "reason": "/backup、/execution、/preservation 中的哈希与日志只在证据内部自证：E:\\codex\\Re0\\Mathbench Discovery 及其第三阶段本地修订目录在本运行时不可达，recheck.py、核验结果.json、stdout.log、方向1_前20独有候选.csv 均无法直接打开；full_ranking_S.csv 与 full_ranking_C.csv 在本运行时亦不存在（/freeze/verified_files 只有哈希声明）。建议在证据中显式登记这一限制，避免读者把内部自洽当作外部验证。",
      "artifact_refs": [
        "shared/recheck_evidence.json"
      ]
    },
    {
      "observation_id": "observation-5",
      "title": "打平成因为机械结果，不能作为策略等价证据",
      "priority": "P2",
      "reason": "四个独有候选 DFT 距离 −0.347437、−0.31012、−0.309271、−0.30364 全部远低于 0（安全边际 0.30 至 0.35 eV/atom），前 20 附近几乎全为深度稳定相，因此替换名额必然不改变命中数，D20=0 是该池机械结论。成因解释成立，但报告若据此论证 S 与 C 等价会过度解读，策略差异应放到更深档位或含真负类的指标上比较。",
      "artifact_refs": [
        "shared/divergence_4rows.csv",
        "shared/recheck_evidence.json"
      ]
    }
  ]
}
```
