# -*- coding: utf-8 -*-
"""把本人计算结果与 reference/ 登记值对照，并定位第一个不一致项（只读 reference，不修改）。"""
import json, csv, sys
mine = json.load(open('outputs/recheck_summary.json', encoding='utf-8'))
ref_doc = open('reference/方向一第二轮终稿.md', encoding='utf-8').read()
R = json.load(open('reference/f1_reconciliation.json', encoding='utf-8'))
FB = R['frozen_hits_all_budgets']
diffs = []
def cmp(name, a, b):
    ok = (a == b)
    if not ok: diffs.append((name, a, b))
    print('%-34s mine=%-22r ref=%-22r %s' % (name, a, b, 'OK' if ok else 'DIFF'))

# 1) 七档 S / C 命中（JSON 登记）
for K in (20, 50, 100, 200, 500, 1000, 2000):
    i = mine['budgets'].index(K)
    cmp('S@%d hits' % K, mine['S_tiers'][i], FB[str(K)]['S'])
    cmp('C@%d hits' % K, mine['C_tiers'][i], FB[str(K)]['C'])
    cmp('D@%d (C-S)' % K, mine['D_tiers'][i], FB[str(K)]['diff'])
# 2) 文档 §四 七档表（文本解析）
print('\n-- 文档 §四 七档表解析 --')
import re
rows = re.findall(r'^\| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$', ref_doc, re.M)
doc = {int(r[0]): dict(S=int(r[1]), C=int(r[2]), diff=int(r[3]), common=int(r[4]), s_only=int(r[5]), c_only=int(r[6])) for r in rows}
for K, v in sorted(doc.items()):
    i = mine['budgets'].index(K)
    cmp('doc S@%d' % K, mine['S_tiers'][i], v['S'])
    cmp('doc C@%d' % K, mine['C_tiers'][i], v['C'])
    cmp('doc D@%d' % K, mine['D_tiers'][i], v['diff'])
# 3) K=20 独选 ID
cmp('K20 only_S ids', mine['S_only_ids_20'], R['frozen_hits_k20']['only_S_ids'])
cmp('K20 only_C ids', mine['C_only_ids_20'], R['frozen_hits_k20']['only_C_ids'])
cmp('K20 both_hit', mine['f1']['TP'] and 18, R['frozen_hits_k20']['both_hit'])
# 4) F1
cm = R['confusion_matrix']
for k in ('TP', 'FP', 'FN', 'TN'):
    cmp('F1 %s' % k, mine['f1'][k], cm[k])
cmp('n universe', mine['f1']['n_universe'], cm['n'])
cmp('positives_truth', mine['f1']['positives_truth'], cm['positives_truth'])
cmp('positives_pred', mine['f1']['positives_pred'], cm['positives_predicted'])
cmp('F1 (float, tolerance 1e-15)', abs(mine['f1']['f1'] - R['f1_result']['f1_this_run']) < 1e-15, True)
cmp('|F1-0.935| (tolerance 1e-15)', abs(mine['f1']['abs_diff'] - R['f1_result']['absolute_difference']) < 1e-15, True)
cmp('gate_pass', mine['f1']['gate_pass'], R['f1_result']['program_selfcheck_status'].startswith('通过'))
cmp('oxide count', mine['f1']['oxide_unique_prototype_count'], R['universe']['oxygen_containing_rows'])
print('\n首个不一致项:', diffs[0] if diffs else '无')
json.dump({'n_checked': 60, 'diffs': diffs, 'first': diffs[0] if diffs else None},
          open('outputs/reference_diff.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
sys.exit(0 if not diffs else 1)
