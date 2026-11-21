# 【组会前一晚｜材料科学】有限预算下预测模型的决策组

材料研究生只有 20 个 DFT 复核名额时，该把哪些含氧化合物放在名单最前面？本项目用 Mira 五人专家团在同一 WBM 候选池比较两种决策。策略 S 按预先选定的单模型预测凸包距离排序，策略 C 按每个材料在入选模型上的预测凸包距离中位数排序。两份名单冻结后，用已有 DFT 参考值评估各自命中数。

当前仓库提供规则、提示词、输入索引和已找回的脚本。盲态交接记录覆盖 23,821 个候选、15 个模型。正式排序程序的原件、端到端复跑及 DFT 命中结论仍待核验。

## 按目录阅读

|部分|可用材料|待补|
|---|---|---|
|规则|[预注册原文](rules/9-预注册规则.md)、[偏离与执行缺项](rules/deviations.md)|团队签认与冻结凭证|
|工作流与 Agent|[五位成员配置](workflow/Mira五人专家团_五位成员SystemPrompt.md)、[阶段一提示词](workflow/第一阶段_盲排与冻结.md)、[阶段二提示词](workflow/第二阶段_揭晓与复核.md)、[运行指南](workflow/运行指南.md)|Mira 专家团分享链接|
|输入|[16 项下载地址与 MD5](inputs/downloads.csv)、[盲态交接证据](evidence/node_1_data_handoff.md)|团队原件《可行性报告.md》及用来复算范围的 scope.py|
|代码|[参考凸包能量提取](code/make_ref.py)、[合成测试用排序脚本](code/synthetic/rank.py)、[名单交集核对](compare_lists.py)|正式版 rank.py、揭晓脚本、independent_check.py 及其使用说明|
|结果与文档|计划在运行及核验完成后发布|冻结名单、freeze.json、逐材料结果表与图、研究报告、一页说明和海报|

## 怎么复跑

1. **校验输入。** 按清单的 Figshare 链接下载需要的压缩文件到仓库外，以下载原件计算 MD5。Windows PowerShell 可运行下列命令，将文件名换成实际保存路径。清单中的 16 个 MD5 已用本地压缩文件逐项核对。

   ```powershell
   Get-FileHash -Algorithm MD5 -LiteralPath .\64706751.gz
   ```

2. **在 Mira 执行。** 按运行指南导入五个岗位，先执行盲排与冻结。收齐签认、总指纹和时间回执后执行揭晓与独立复核。完整重建正式名单仍依赖表中待补文件。

3. **单独核对已有名单。** 已持有 Mira 导出的七档名单时，用 Python 3 执行下面的命令。输出包括预算、共同入选数及两侧独有材料 ID。两档命令已用本地导出文件复测。首批公开包只收录脚本，名单文件随结果发布。

   ```bash
   python compare_lists.py --input "/path/to/node_4_budget_lists.json" --k 20
   python compare_lists.py --input "/path/to/node_4_budget_lists.json" --k 50
   ```

## 数据性质、来源与许可

本研究使用的材料能量和模型预测全部为模拟数据。WBM 的参考形成能与凸包距离来自 DFT 计算，各模型的预测形成能来自机器学习计算。名单、排名和统计量由程序生成。本项目没有新增 DFT 计算或实验测量；计算稳定性不能直接推出可合成性。

数据来自 Janosh Riebesell 等维护的 Matbench Discovery。Figshare 的 Matbench Discovery Data Files 标注 **CC BY 4.0**。团队的处理包括按成分选池、对齐模型预测、计算相对参考凸包的距离及汇总排序。引用和再分发时保留原作者、来源、许可与修改说明；单项资源以其发布页许可为准。[数据集](https://doi.org/10.6084/m9.figshare.22715158) · [预测归档](https://doi.org/10.6084/m9.figshare.28187990) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) · [模型卡固定版本](https://github.com/janosh/matbench-discovery/tree/6d587c184cdb4a4865dc0b15b04a5e6d77ed464f)
