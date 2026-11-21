#!/usr/bin/env python3
"""Python 3.10+ 标准库。工作区根目录运行 python3 shared/recheck_v2.py。
只读 shared/inputs 与 shared/input_verification_v2.json；每次新建 runs/<UTC 时间戳>。
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import shlex
import sys

HULL = 'e_above_hull_mp2020_corrected_ppd_mp'
DFT_FORM = 'e_form_per_atom_mp2020_corrected'
PRED = 'e_form_per_atom'
CARD = '0.935'
# 未找到旧断言的数值容差。默认采用模型卡末位的半单位，可显式覆盖。
DEFAULT_TOL = 0.5 * 10 ** -len(CARD.split('.')[1])
MANIFEST = Path('shared/input_verification_v2.json')
INPUTS = Path('shared/inputs')
FROZEN = INPUTS / 'frozen_stage2'
TOP = {'S': 'S_top20_scored.csv', 'C': 'C_top20_signoff85f13c0c.csv'}
RESULT = 'f1_run_result.json'
DETAIL = 'f1_hits_detail.csv'


def sha256(path):
    with path.open('rb') as f:
        h = hashlib.sha256()
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check_inputs():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    indices = manifest['gz_inputs']
    keys = ('wbm_2023_12_13_summary', 'champion_dpa_prediction')
    paths = tuple(INPUTS / 'source' / filename for filename in (
        '2023-12-13-wbm-summary.csv.gz', 'dpa-4.1-max-oam-pft_2026-10-27-discovery.csv.gz'))
    records = [(p, indices[k]['sha256_recomputed_this_round']) for p, k in zip(paths, keys)]
    frozen = {x['file']: x['sha256'] for x in
              manifest['frozen_stage2_check']['local_copies_verified_this_round']}
    records += [(FROZEN / name, frozen[name]) for name in (
        'freeze.json', 'budget_lists_7tier.json', 'signoff_S.md', 'signoff_C.md', *TOP.values())]
    checks = {}
    for path, expected in records:
        if not path.resolve().is_relative_to(INPUTS.resolve()) or not path.is_file():
            raise ValueError(f'输入缺失或位于授权目录之外：{path}')
        observed = sha256(path)
        if observed != expected:
            raise ValueError(f'SHA-256 不符：{path}；登记={expected}；实际={observed}')
        checks[str(path)] = dict(expected_sha256=expected, actual_sha256=observed, match=True)
    return paths, checks


def id_rows(path, required):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not (set(required) | {'material_id'}).issubset(reader.fieldnames or ()):
            raise ValueError(f'表头缺列：{path}')
        ids = set()
        for row in reader:
            mid = row['material_id']
            if not mid or mid in ids:
                raise ValueError(f'空或重复 material_id：{path}:{reader.line_num} {mid!r}')
            ids.add(mid)
            yield mid, row


def number(text, mid, field):
    try:
        v = float(text)
    except (ValueError, TypeError):
        raise ValueError(f'{mid} 缺少有效数值：{field}') from None
    if not math.isfinite(v):
        raise ValueError(f'{mid} 非有限数值：{field}')
    return v


def budgets():
    data = json.loads((FROZEN / 'budget_lists_7tier.json').read_text(encoding='utf-8'))
    levels = data['budgets']
    for k in levels:
        for strategy in TOP:
            ids = data[strategy][str(k)]
            if len(ids) != k or len(set(ids)) != k:
                raise ValueError(f'{strategy} K={k} 冻结名单长度或唯一性异常')
    for strategy, name in TOP.items():
        rows = list(id_rows(FROZEN / name, ['rank']))
        if [(mid, int(row['rank'])) for mid, row in rows] != [
            (mid, rank) for rank, mid in enumerate(data[strategy][str(len(rows))], 1)
        ]:
            raise ValueError(f'{strategy} 冻结 CSV 与对应预算名单不一致')
    return data


def calculate(wbm, prediction, frozen):
    predictions = {mid: row[PRED] for mid, row in id_rows(prediction, [PRED])}
    targets = {mid for s in TOP for k in frozen['budgets'] for mid in frozen[s][str(k)]}
    labels = {}
    counts = Counter()
    n = 0
    for mid, row in id_rows(wbm, [HULL, DFT_FORM, 'unique_prototype', 'formula']):
        prototype = row['unique_prototype']
        if prototype not in ('True', 'False'):
            raise ValueError(f'{mid} 无效的 unique_prototype={prototype!r}')
        if prototype == 'False' and mid not in targets:
            continue
        hull = number(row[HULL], mid, HULL)
        true = hull <= 0
        if mid in targets:
            labels[mid] = (row['formula'], hull, true)
        if prototype == 'True':
            form = number(row[DFT_FORM], mid, DFT_FORM)
            pred = number(predictions.get(mid), mid, PRED)
            predicted = pred - (form - hull) <= 0
            counts[('tp' if true else 'fp') if predicted else ('fn' if true else 'tn')] += 1
            n += 1
    missing = targets - labels.keys()
    if missing:
        raise ValueError(f'WBM 缺少 {len(missing)} 个冻结材料 ID：{sorted(missing)[:5]}')
    matrix = {k: counts[k] for k in ('tp', 'fp', 'tn', 'fn')}
    denominator = 2 * matrix['tp'] + matrix['fp'] + matrix['fn']
    if n != sum(matrix.values()) or not denominator:
        raise ValueError('四格计数不一致或 F1 无定义')
    return n, matrix, 2 * matrix['tp'] / denominator, labels


def write_hits(path, run_id, frozen, labels):
    summaries = {}
    with path.open('x', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['run_id', 'budget_k', 'material_id', 'formula', HULL,
                    's_rank', 'c_rank', 's_hit', 'c_hit'])
        for k in frozen['budgets']:
            s, c = ({mid: r for r, mid in enumerate(frozen[key][str(k)], 1)} for key in TOP)
            sh = {mid for mid in s if labels[mid][2]}
            ch = {mid for mid in c if labels[mid][2]}
            # 并集每个材料一行；空 rank + 空 hit 表示未入选，不等于 false。
            for mid in dict.fromkeys((*s, *c)):
                formula, hull, hit = labels[mid]
                flag = str(hit).lower()
                w.writerow([run_id, k, mid, formula, hull, s.get(mid), c.get(mid),
                            flag if mid in s else '', flag if mid in c else ''])
            summaries[str(k)] = dict(S_hits=len(sh), C_hits=len(ch),
                                     C_minus_S=len(ch)-len(sh), absolute_hit_difference=abs(len(ch)-len(sh)),
                                     both_hit=len(sh & ch), only_S_hit=len(sh - ch), only_C_hit=len(ch - sh))
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--f1-tolerance', type=float, default=DEFAULT_TOL)
    args = parser.parse_args()
    if not math.isfinite(args.f1_tolerance) or args.f1_tolerance < 0:
        parser.error('--f1-tolerance 须为有限非负值')
    (wbm, prediction), checks = check_inputs()
    now = datetime.now(timezone.utc)
    run_id = now.strftime('%Y%m%dT%H%M%S%fZ')
    run_dir = Path('runs') / run_id
    command = shlex.join(sys.orig_argv)
    script_sha = sha256(Path(__file__))
    frozen = budgets()
    n, matrix, f1, labels = calculate(wbm, prediction, frozen)
    run_dir.mkdir(parents=True, exist_ok=False)
    hits_file = run_dir / DETAIL
    hit_counts = write_hits(hits_file, run_id, frozen, labels)
    diff = abs(f1 - float(CARD))
    passed = diff <= args.f1_tolerance
    top20 = hit_counts['20']
    summary = (f'{run_id} | n={n} | TP={matrix["tp"]} FP={matrix["fp"]} '
               f'TN={matrix["tn"]} FN={matrix["fn"]} | F1={f1!r} | '
               f'card_f1={CARD} | absolute_difference={diff!r} | passed={str(passed).lower()} | '
               f'K=20 S={top20["S_hits"]} C={top20["C_hits"]} C−S={top20["C_minus_S"]}')
    result = dict(run_id=run_id, run_timestamp_utc=now.isoformat(), run_dir=str(run_dir),
                  command=command, script_sha256=script_sha,
                  published_rerun_command=f'python3 shared/recheck_v2.py --f1-tolerance {args.f1_tolerance!r}',
                  model='dpa-4.1-max-oam-pft', universe='WBM unique_prototype=True; all chemical systems; join on material_id',
                  truth_rule=f'{HULL} <= 0',
                  predicted_distance_formula=f'{PRED} - ({DFT_FORM} - {HULL})',
                  prediction_rule='predicted_distance <= 0', f1_formula='2*TP/(2*TP+FP+FN)',
                  n=n, **matrix, f1=f1, card_f1=float(CARD), absolute_difference=diff,
                  passed=passed, f1_gate=dict(rule='absolute_difference <= tolerance', tolerance=args.f1_tolerance,
                  default_basis='half the last displayed model-card unit; historical assertion tolerance not documented in available evidence'),
                  input_verification=dict(manifest=str(MANIFEST), manifest_sha256=sha256(MANIFEST),
                                          all_match=True, files=checks),
                  frozen_hit_rule=f'Frozen list membership joined to original WBM by material_id; hit iff {HULL} <= 0',
                  frozen_hits_by_budget=hit_counts, hits_detail_file=DETAIL,
                  hits_detail_sha256=sha256(hits_file), stdout_file='stdout.log', report_summary=summary)
    with (run_dir / RESULT).open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    (run_dir / 'stdout.log').write_text(summary + '\n', encoding='utf-8')
    print(summary)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f'复算停止：{exc}') from None
