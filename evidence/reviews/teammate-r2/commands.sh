#!/bin/sh
# 复核岗全部实跑命令。执行位置：解压后的「队友复验工作空间」根目录。
# 0) 解压（务必用 Python zipfile，shell unzip 会把 UTF-8 中文名按 GBK 误解码）
#    python3 -c "import zipfile;zipfile.ZipFile('shared/input.zip').extractall('ws')"
#    cd ws/队友复验工作空间
# 1) 指纹：包内清单 + freeze.json 对照
sha256sum -c SHA256SUMS.txt
sha256sum results/budget_lists_7tier.json results/freeze.json
# 2) 主路径：冠军 F1 自检 + 冻结七档计数 + 前20逐行 + 共同/独选
python3 outputs/recheck_champion_and_lists.py --root . --out outputs
# 3) 第二对照路径（工作空间自带便携脚本）
python3 code/recount.py raw/64706751.gz raw/70836372.gz | tee outputs/recount_cli_stdout.txt
