# 【B·组会前一晚｜材料科学】有限预算下预测模型的决策组

评审导读：[历史溯源与版本沿革](docs/历史溯源与版本沿革.md) · [术语与判定口径](docs/术语与判定口径.md)

研究生只有 20 个 DFT 复核名额时，是按单模型冠军选材料，还是取 15 个模型的共识？本项目在 Matbench Discovery 的 23,821 个含氧候选上先盲排、冻结名单，再按公开 DFT 凸包距离 ≤ 0 eV/atom 计数。输入能量均为计算模拟值，名单和统计由代码生成。

## 最新验证结果

方向一第二轮按全体系 215,488 个独特原型复算，主算与 Mira 独立复核脚本均得到 F1=0.9346141647，与模型卡 0.935 相差 0.000386，满足预注册门槛 0.02。另一位真人队员的独立复跑与签认待补。 排序复现的范围为已交接的含氧盲表。方向一复核岗从原始总体重建 S 子池时报告首位差异，子池筛选定义仍需对照；其复核环境也未独立重建 C 的全部模型分数。

[方向一修订终稿](evidence/reviews/direction1-v2/final_report_v2.md) · [结构化结论](evidence/reviews/direction1-v2/f1_reconciliation.json) · [独立复核记录](evidence/reviews/direction1-v2/independent_review_v2.md) · [研究报告](docs/研究报告.md)

## 11 月 21 日交付入口

- [三阶段工作流和五位专家配置](workflow/current/)包含角色、底座、关联 Skills 与提示词。角色卡列出配置用途，实际调用以对应会话可导出的记录为准。
- [预注册规则](rules/9-预注册规则.md)、[修订记录](rules/deviations.md)、[实际盲排输入](inputs/blind/)、[排序配置和重建程序](code/reconstructed/)对应 Mira 会话「有限预算下S与C命中对比-l8dpcu47」。
- [冻结回执与结果](results/)包括两份全排序、预测稳定集合、七档有序名单、两份前 20 明细、四个独选候选和复算输出。来源为上述会话及「第三阶段修订复算与四候选核对-pxmxf8pg」。[原揭晓版本](evidence/superseded/)来自「恢复第三阶段揭晓与冠军F1核算-hpp5x5x4」。
- [项目说明与演示](docs/项目说明.md) · [已交海报](docs/poster.png) · [方向一复核意见](evidence/reviews/)。工作流通过跨会话恢复及修订形成这批产物，另一个队员的独立复跑待登记。

## 关键步骤复跑

从仓库根目录运行。盲排使用 Python 和 NumPy（本次复测 2.3.5），读取随仓库提供的派生盲表。原始压缩数据通过下载清单取得。

~~~sh
python -m pip install numpy==2.3.5
python code/reconstructed/rank_formal.py --pool inputs/blind/unlabeled_candidate_pool.csv --ref inputs/blind/reference_hull_energies.csv --manifest inputs/blind/model_manifest.json --outdir replay
~~~

核对 replay/budget_lists_7tier.json 与 results/budget_lists_7tier.json 的 S、C 七档 ID 及顺序。两侧七档在本次复测中逐项相同。

揭晓复算只需 Python 3.11+ 标准库。按[下载清单](inputs/downloads.csv)取 WBM（64706751）和冠军预测（70836372），将下方两个参数换成下载文件的实际路径。脚本先校验压缩原件及冻结预算名单 SHA-256，再按材料 ID 关联。

~~~sh
python code/recount.py /path/to/64706751.gz /path/to/70836372.gz
~~~

与 [本地实跑输出](results/recount.txt)核对。215,488 个独特原型上 F1 为 0.9346141647。20 个名额两边各中 20，2,000 个名额单模型中 1,935、共识中 1,946。结论限于该候选池、模型版本及预算。

## 数据来源和许可

WBM 参考能量来自 DFT，模型预测来自机器学习。本研究复用公开模拟数据，未新增实验测量。数据集标注 CC BY 4.0，各单项资源按其发布页许可使用；处理包括按成分筛选、对齐预测、排序及揭晓。[Matbench Discovery 数据](https://doi.org/10.6084/m9.figshare.22715158) · [预测归档](https://doi.org/10.6084/m9.figshare.28187990) · [许可](https://creativecommons.org/licenses/by/4.0/)
