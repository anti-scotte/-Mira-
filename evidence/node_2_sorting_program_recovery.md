# 本轮 S/C 排序程序查找记录

**正式程序尚未找回。** S 签认给出了程序名 `rank.py` 和版本 `1.0.0-formal-distance`，但没有源码指纹或执行命令。现有名单、签认和旧测试报告均保留，未改写。

## 已查证的文件

|位置|发现|能证明什么|
|---|---|---|
|本机工作空间 1：`E:\Mathbench Discovery\Mira产物\自动执行缺少文件的联网检索计划-pv2slx1f\node_4_7f0af346-b198-4858-9cbf-78e026eb3d88\第1轮-0c58e160`|含 `S_signoff.json`、`ranking_outputs.md`、`S_full_ranking.csv`、`C_full_ranking.csv`、`budget_lists.json`、`prediction_stability_sets.json`；递归列出含隐藏项，无其他文件。|签认和运行摘要确定版本名、输入和产物；摘要不是完整执行日志，目录没有正式脚本。|
|当前 `shared/`|已查目录，核对同名 S 签认、运行摘要及 `ranking_synthetic_test.md`。|有输出与历史测试，但没有已绑定的正式入口。|
|本机 `E:\Mathbench Discovery\Mira产物\自动执行缺少文件的联网检索计划-pv2slx1f\node_2_7f0af346-b198-4858-9cbf-78e026eb3d88\第1轮-0c58e160\scratch\rank.py`|`Get-FileHash -Algorithm SHA256` 实测 `bd9fc77aa55b38075bf30057377186ffb86a87b09850cdb89c866854a1298217`，源码首行标为 `1.0.0`。|逐字节指纹匹配旧合成测试报告，不是正式版本的身份证明。旧版接收三张拆分 CSV 并输出 JSON；未找到正式运行使用它或其包装器的证据。|

## 最快补件方式（无需修改文件）

1. [定位原会话消息](sciclaw://sessions/pv2slx1f/messages/05295261-9b9d-4162-b7f1-1dcfbbd2acb5)，打开「自动执行缺少文件的联网检索计划」的历史任务，选**第 1 轮、节点 4**。用产物 `S_signoff.json` 和 `ranking_outputs.md` 识别任务，不要选仅输出 `ranking_synthetic_test.md` 的节点 2。上表给出可直接粘贴到资源管理器地址栏的节点 4 目录。
2. 在该任务的附件或执行记录中查找生成 `S_full_ranking.csv` 和 `C_full_ranking.csv` 的 **`rank.py`（签认版本 `1.0.0-formal-distance`）**，下载原文件及当时的启动命令和所引用配置。若当时以内联程序运行，请导出含完整原始代码、参数和工作目录的那一步执行记录，不要按报告重写。历史页面中是否仍可下载尚未验证，无已核实的脚本直链。
3. 将上述文件作为输入附件上传至当前**节点 2「查找并测试本轮正式排序程序」**；若只能在会话发附件，注明绑定此节点。无需编辑、改名或上传名单、真实材料数据、DFT 标签。若历史记录也没有原件，请告知缺失，不必上传旧 `rank.py`。
