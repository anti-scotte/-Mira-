# 【B·组会前一晚｜材料科学】有限预算下预测模型的决策组

**Demo** · [Mira 专家团配置分享](https://mira.deepprinciple.com/share/squad/txWEoOX5YRIy3Bx8zEXUtQ)　**现场复算** · [下载含两份原始输入的独立工作空间](workflow/指标敏感性专家团/四环节独立复验工作空间.zip)

复验包默认同时执行主实验与指标子实验。自首个执行节点启动起共用 60 分钟，两项结果分别输出；到时交付已完成部分及缺项。

**作品对话分享** · 冻结名单复验（vkbyw0ev）与 DAF 扩展（zzqvuo1g）的公开对话链接待生成。当前 Demo 链接可打开四环节专家团配置。

评审导读：[历史溯源与版本沿革](docs/历史溯源与版本沿革.md) · [术语与判定口径](docs/术语与判定口径.md)

研究生只有 20 个 DFT 复核名额时，是按单模型冠军选材料，还是取 15 个模型的共识？本项目在 Matbench Discovery 的 23,821 个含氧候选上先盲排、冻结名单，再按公开 DFT 凸包距离 ≤ 0 eV/atom 计数。输入能量均为计算模拟值，名单和统计由代码生成。

## 评审验收进度

| 状态 | 可核对的结果 | 交付入口 |
|---|---|---|
| 主实验与方向一修订已完成 | 前 20 共同入选 18 个，两侧独选各 2 个且均命中。修正预测距离换算后，冠军 F1 为 0.9346141647。 | [方向一修订终稿](evidence/reviews/direction1-v2/final_report_v2.md) · [研究报告](docs/研究报告.md) |
| 队友独立复算 R1 已完成 | 独立会话沿用冻结名单，从原始文件复算冠军 F1 和七档命中。K=20 两侧均为 20/20；K=2000 共识 1946、单模型 1935。 | [R1 复核摘要](evidence/reviews/teammate-r1/复核摘要.md) · [七档计数](evidence/reviews/teammate-r1/tier_summary.csv) · [队友填写的签认](evidence/reviews/teammate-r1/02_真人签认_本人填写.txt) |
| 队友独立复验 R2 | 傅誉发起独立会话并实名签认，56 项对照一致，冻结名单复算约 16 分钟。 | [会话说明与签认原件](evidence/reviews/teammate-r2/) |
| 组长四环节复跑 | 揭晓后再次得到主实验七档计数；预检已读取 reference，环节③受理登记受阻。 | [四环节输出与证据边界](evidence/reviews/four-stage-replay/) |
| 事后扩展 · DAF | 换指标后，20 个名额换 1 项且仍为 20/20；2000 个名额比原单模型多中 4 项。 | [队友扩展七档结果](evidence/reviews/extension-daf/) |

R1 验证的是冻结后的揭晓和计数。从已交接盲表重排的检查见下方复跑说明；方向一审核使用全体系 215,488 项排序，冻结名单取 23,821 项含氧共同池。R1 从原始 WBM 识别的含氧 ID 集合与盲表完全相同，详见 R1 摘要第五节。

## 11 月 21 日交付入口

- [三阶段工作流和五位专家配置](workflow/current/)包含角色、底座、关联 Skills 与提示词。角色卡列出配置用途，实际调用以对应会话可导出的记录为准。
- [预注册规则](rules/9-预注册规则.md)、[修订记录](rules/deviations.md)、[实际盲排输入](inputs/blind/)、[排序配置和重建程序](code/reconstructed/)对应 Mira 会话「有限预算下S与C命中对比-l8dpcu47」。
- [冻结回执与结果](results/)包括两份全排序、预测稳定集合、七档有序名单、两份前 20 明细、四个独选候选和复算输出。来源为上述会话及「第三阶段修订复算与四候选核对-pxmxf8pg」。[原揭晓版本](evidence/superseded/)来自「恢复第三阶段揭晓与冠军F1核算-hpp5x5x4」。
- [项目说明与演示](docs/项目说明.md) · [已交海报](docs/poster.png) · [方向一复核意见](evidence/reviews/)。工作流通过跨会话恢复及修订形成这批产物，后续 R1 复验另存于上表所列目录。

队友 R1 的签认“你好”为群昵称。该会话由队友发起，Mira 成员执行计算，队友核对输出。签认原件保留在上表所列目录。

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

## 扩展实验与运行记录

[新窗口任务书及复核口径](docs/扩展实验_新窗口任务书.md) · [历史问题与恢复记录](docs/Mira运行停止与应对记录.md)
