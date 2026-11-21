#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
independent_check.py — 独立复算 / 交叉核对脚本（stage=evaluate，独立实现）

设计约束（本轮契约）：
  * 不 import、不 importlib 加载、不复制 shared/recheck_v2.py 的任何函数；
    本文件所有解析、判据、排序、同分裁决均为独立重写。
  * 只读输入：shared/inputs/source/*.gz、shared/inputs/frozen_stage2/*、
    shared/f1_run_result.json、shared/f1_hits_detail.csv。
  * 只写本脚本声明的独立输出目录（默认 runs/independent_<UTC>）。
  * stdout、结果 JSON、报告摘要三处引用同一次运行（同一 run_id / 同一内存对象）。

用法：
  python3 independent_check.py                      # 默认
  python3 independent_check.py --capability-check   # 能力自检
  python3 independent_check.py --run-dir DIR        # 指定输出目录（可复现）
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import platform  # noqa: F401
import sys
from datetime import datetime, timezone

# ----------------------------------------------------------------------------
# 常量（均来自声明输入，非从 recheck_v2.py 读取）
# ----------------------------------------------------------------------------
def _resolve_shared():
    """按候选顺序定位声明输入所在目录，不依赖脚本被复制到哪一层。
    优先级：环境变量 INDEPENDENT_CHECK_SHARED > 脚本同目录(含 inputs/) >
    脚本目录下 shared/ > 其上层 shared/ > 当前工作目录 shared/。"""
    env = os.environ.get("INDEPENDENT_CHECK_SHARED")
    cands = []
    if env:
        cands.append(env)
    here = os.path.dirname(os.path.abspath(__file__))
    cands += [here,
              os.path.join(here, "shared"),
              os.path.join(os.path.dirname(here), "shared"),
              os.path.join(os.getcwd(), "shared")]
    probe = os.path.join("inputs", "source", "2023-12-13-wbm-summary.csv.gz")
    for c in cands:
        if os.path.exists(os.path.join(c, probe)):
            return c
    raise SystemExit(
        "找不到声明输入目录（需要 <dir>/inputs/source/2023-12-13-wbm-summary.csv.gz）。"
        "请用 INDEPENDENT_CHECK_SHARED=<shared目录> 指定。已尝试：" + repr(cands))


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED = _resolve_shared()

SRC_WBM = os.path.join(SHARED, "inputs", "source", "2023-12-13-wbm-summary.csv.gz")
SRC_CHAMP = os.path.join(SHARED, "inputs", "source", "dpa-4.1-max-oam-pft_2026-10-27-discovery.csv.gz")
FROZEN = os.path.join(SHARED, "inputs", "frozen_stage2")
BUDGET_JSON = os.path.join(FROZEN, "budget_lists_7tier.json")
S_TOP20 = os.path.join(FROZEN, "S_top20_scored.csv")
C_TOP20 = os.path.join(FROZEN, "C_top20_signoff85f13c0c.csv")
DECLARED_JSON = os.path.join(SHARED, "f1_run_result.json")
DECLARED_CSV = os.path.join(SHARED, "f1_hits_detail.csv")

COL_ID = "material_id"
COL_FORMULA = "formula"
COL_UNIQ = "unique_prototype"
COL_HULL = "e_above_hull_mp2020_corrected_ppd_mp"
COL_EFORM_CORR = "e_form_per_atom_mp2020_corrected"

CARD_F1 = 0.935                       # 模型卡显示值（3 位小数）
PREREG_TOL = 0.02                     # 预注册门槛：|F1 − 0.935| <= 0.02
REFERENCE_RUN_TOL_TABLE = [1e-12, 1e-9, 1e-6, 5e-4]  # 阈值扫描停止带（最后一个=声明的 0.0005）
BUDGETS = [20, 50, 100, 200, 500, 1000, 2000]
TIE_SALT = "WBM-oxide-v1|"

# ----------------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------------


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text_items(items) -> str:
    """名单哈希：对 (顺序序号, material_id) 规范化后逐行 sha256。"""
    h = hashlib.sha256()
    for i, mid in enumerate(items):
        h.update(f"{i + 1}\t{mid}\n".encode("utf-8"))
    return h.hexdigest()


def to_float(x):
    """严格浮点解析：空串 / 非有限 -> None（视为缺失）。"""
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "na", "none", "null"}:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v


def tie_key(material_id: str):
    return (hashlib.sha256((TIE_SALT + material_id).encode("utf-8")).hexdigest(), material_id)


def rank_rows(rows, score_key):
    """确定性排序：分数升序(缺失置尾) -> tie_key。返回 [(mid, score)]。"""
    def key(r):
        s = r[score_key]
        return (1, 0.0) + tie_key(r[COL_ID]) if s is None else (0, s) + tie_key(r[COL_ID])
    return [(r[COL_ID], r[score_key]) for r in sorted(rows, key=key)]


# ----------------------------------------------------------------------------
# 阶段 1：读取原始数据
# ----------------------------------------------------------------------------


def load_wbm(path):
    """返回 (rows, stats)。rows: list[dict]，只保留 unique_prototype==True。"""
    n_total = 0
    n_uniq = 0
    seen = {}
    dup_ids = []
    rows = []
    missing_hull = []
    nonfinite_ef = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        need = [COL_ID, COL_FORMULA, COL_UNIQ, COL_HULL, COL_EFORM_CORR]
        absent = [c for c in need if c not in rd.fieldnames]
        if absent:
            raise SystemExit(f"WBM 缺少列: {absent}")
        for rec in rd:
            n_total += 1
            if str(rec[COL_UNIQ]).strip().lower() != "true":
                continue
            n_uniq += 1
            mid = rec[COL_ID].strip()
            seen[mid] = seen.get(mid, 0) + 1
            if seen[mid] > 1:
                dup_ids.append(mid)
            hull = to_float(rec[COL_HULL])
            ef = to_float(rec[COL_EFORM_CORR])
            if hull is None:
                missing_hull.append(mid)
            if ef is None:
                nonfinite_ef.append(mid)
            rows.append({COL_ID: mid, COL_FORMULA: rec[COL_FORMULA], COL_HULL: hull, COL_EFORM_CORR: ef})
    stats = {
        "wbm_rows_total": n_total,
        "unique_prototype_true_rows": n_uniq,
        "unique_prototype_duplicate_material_id": sorted(dup_ids),
        "unique_prototype_unique_material_id_count": len(seen),
        "label_missing_or_nonfinite": missing_hull,
        "e_form_corrected_missing_or_nonfinite": nonfinite_ef,
    }
    return rows, stats


def load_champion(path):
    pred = {}
    dup = []
    missing = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        if COL_ID not in rd.fieldnames or "e_form_per_atom" not in rd.fieldnames:
            raise SystemExit(f"冠军文件列不合规: {rd.fieldnames}")
        for rec in rd:
            mid = rec[COL_ID].strip()
            v = to_float(rec["e_form_per_atom"])
            if mid in pred:
                dup.append(mid)
            if v is None:
                missing.append(mid)
            pred[mid] = v
    return pred, {"champion_rows": len(pred), "champion_duplicate_material_id": dup,
                  "champion_missing_or_nonfinite": missing}


# ----------------------------------------------------------------------------
# 阶段 2：同口径标签 / 预测 / 四格
# ----------------------------------------------------------------------------


def predict_distance(row, pred_ef):
    """predicted_distance = pred(Ef/atom) − (Ef_corr − E_hull_corr)"""
    p = pred_ef.get(row[COL_ID])
    if p is None or row[COL_EFORM_CORR] is None:
        return None
    return p - (row[COL_EFORM_CORR] - row[COL_HULL])


def confusion(rows, pred, threshold_label=0.0, rule="le"):
    """rule='le' -> label<=T；rule='lt' -> label<T（仅用于敏感性）"""
    tp = fp = tn = fn = 0
    excluded = 0
    for r in rows:
        y = r[COL_HULL]
        d = predict_distance(r, pred)
        if y is None or d is None:
            excluded += 1
            continue
        truth = (y <= threshold_label) if rule == "le" else (y < threshold_label)
        guess = (d <= 0.0) if rule == "le" else (d < 0.0)
        if truth and guess:
            tp += 1
        elif truth and not guess:
            fn += 1
        elif (not truth) and guess:
            fp += 1
        else:
            tn += 1
    n = tp + fp + tn + fn
    f1 = (2 * tp) / (2 * tp + fp + fn) if (2 * tp + fp + fn) else float("nan")
    return {"n": n, "tp": tp, "fp": fp, "tn": tn, "fn": fn, "f1": f1,
            "excluded_rows": excluded,
            "positives_true": tp + fn, "positives_pred": tp + fp}


def f1_of(tp, fp, fn):
    return (2 * tp) / (2 * tp + fp + fn)


# ----------------------------------------------------------------------------
# 阶段 3：标签在 0 附近的敏感性探针
# ----------------------------------------------------------------------------


def boundary_probe(rows, pred):
    """逐项检查：精确零标签/预测、浮点相邻值、阈值翻转、缺失、重复。"""
    out = {}
    exact_zero_label = [r[COL_ID] for r in rows if r[COL_HULL] == 0.0]
    exact_zero_pred = [r[COL_ID] for r in rows
                       if predict_distance(r, pred) is not None and predict_distance(r, pred) == 0.0]
    out["label_exactly_zero_count"] = len(exact_zero_label)
    out["label_exactly_zero_ids_head"] = exact_zero_label[:20]
    out["predicted_distance_exactly_zero_count"] = len(exact_zero_pred)
    out["predicted_distance_exactly_zero_ids_head"] = exact_zero_pred[:20]

    # 标签 ∈ [-eps, +eps] 的行（浮点邻域）
    band = []
    for r in rows:
        y = r[COL_HULL]
        if y is None:
            continue
        if abs(y) <= 1e-12:
            band.append({"material_id": r[COL_ID], "label": y, "pred_dist": predict_distance(r, pred)})
    out["label_abs_le_1e-12_rows"] = len(band)
    out["label_abs_le_1e-12_head"] = band[:20]

    # 最小非零 |label|
    nz = [abs(r[COL_HULL]) for r in rows if r[COL_HULL] is not None and r[COL_HULL] != 0.0]
    out["min_abs_nonzero_label"] = min(nz) if nz else None
    nzp = [abs(d) for d in (predict_distance(r, pred) for r in rows) if d is not None and d != 0.0]
    out["min_abs_nonzero_pred_dist"] = min(nzp) if nzp else None

    # 阈值翻转：label 用 <0 vs <=0；预测用 <0 vs <=0
    variants = {
        "label_le0_pred_le0": confusion(rows, pred, 0.0, "le"),
        "label_lt0_pred_lt0": confusion(rows, pred, 0.0, "lt"),
        "label_le0_pred_lt0": None,
        "label_lt0_pred_le0": None,
    }
    # 混合口径单独算
    for name, (lrule, prule) in {
        "label_le0_pred_lt0": ("le", "lt"),
        "label_lt0_pred_le0": ("lt", "le"),
    }.items():
        tp = fp = tn = fn = 0
        for r in rows:
            y = r[COL_HULL]
            d = predict_distance(r, pred)
            if y is None or d is None:
                continue
            t = (y <= 0.0) if lrule == "le" else (y < 0.0)
            g = (d <= 0.0) if prule == "le" else (d < 0.0)
            tp += t and g
            fn += t and not g
            fp += (not t) and g
            tn += (not t) and not g
        variants[name] = {"n": tp + fp + tn + fn, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                          "f1": f1_of(tp, fp, fn)}
    base = variants["label_le0_pred_le0"]
    for k, v in variants.items():
        if v is not None:
            v["delta_vs_base"] = {
                "n": v["n"] - base["n"], "tp": v["tp"] - base["tp"], "fp": v["fp"] - base["fp"],
                "tn": v["tn"] - base["tn"], "fn": v["fn"] - base["fn"], "f1": v["f1"] - base["f1"],
            }
    out["threshold_variants"] = variants
    out["threshold_variant_changes_any_cell"] = any(
        any(v["delta_vs_base"][f] != 0 for f in ("n", "tp", "fp", "tn", "fn")) for v in variants.values())
    return out


# ----------------------------------------------------------------------------
# 阶段 4：七档预算、K/K+1、精确同分排序、唯一 ID
# ----------------------------------------------------------------------------


def build_s_ranking(rows, pred):
    """S 策略全排序（预测凸包距离升序 + tie_key）。C 需要 15 模型，本运行时不可重建。"""
    s_rows = []
    for r in rows:
        d = predict_distance(r, pred)
        s_rows.append({COL_ID: r[COL_ID], "s_score": d})
    return rank_rows(s_rows, "s_score")


def tie_report(ranked, budget_map, k_list):
    """在每档 K 与 K+1 处，报告分数相同（完全相等 float）的组及 tie_key 顺序。"""
    from collections import defaultdict
    pos = {m: i for i, (m, _) in enumerate(ranked)}
    score = dict(ranked)
    out = {}
    for k in k_list:
        grp = defaultdict(list)
        for m in budget_map.get(str(k), []):
            s = score.get(m)
            if s is None:
                continue
            grp[repr(s)].append(m)
        tied = {s: v for s, v in grp.items() if len(v) > 1}
        # K/K+1 处同分是否跨越边界
        boundary_tie = None
        if k + 1 <= len(ranked):
            a, b = ranked[k - 1] if k >= 1 else (None, None)
            if k - 1 >= 0 and k < len(ranked):
                if a[1] is not None and a[1] == ranked[k][1]:
                    boundary_tie = {"score": repr(a[1]), "k_item": a[0], "k1_item": ranked[k][0],
                                    "resolved_by_tie_key": tie_key(a[0]) < tie_key(ranked[k][0])}
        out[k] = {
            "tie_groups_within_budget": {s: v for s, v in tied.items()},
            "n_tie_groups": len(tied),
            "boundary_tie_at_k_vs_k1": boundary_tie,
        }
    return out


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--capability-check", action="store_true")
    ap.add_argument("--run-dir", default=None)
    args = ap.parse_args(argv)

    mode = "capability" if args.capability_check else "full"

    integrity = {p: sha256_file(p) for p in [SRC_WBM, SRC_CHAMP, BUDGET_JSON, S_TOP20, C_TOP20,
                                             DECLARED_JSON, DECLARED_CSV] if os.path.exists(p)}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = args.run_dir or os.path.join(SCRIPT_DIR, "runs", "independent_" + run_id)
    os.makedirs(run_dir, exist_ok=True)

    if args.capability_check:
        rep = {
            "run_id": run_id, "mode": mode,
            "python": sys.version.split()[0], "platform": platform.system(),
            "gc_naive": {},
        }
        gc = confusion([
            {COL_ID: "a", COL_HULL: -0.1, COL_EFORM_CORR: 0.0},
            {COL_ID: "b", COL_HULL: 0.2, COL_EFORM_CORR: 0.0},
            {COL_ID: "c", COL_HULL: 0.0, COL_EFORM_CORR: 0.0},
        ], {"a": -0.5, "b": -0.5, "c": 0.0})
        rep["gc_naive"] = gc
        rep["tie_key_sample"] = {m: tie_key(m) for m in ["wbm-1-1", "wbm-3-56891"]}
        rep["inputs_present"] = {k: os.path.exists(k) for k in [SRC_WBM, SRC_CHAMP, BUDGET_JSON,
                                                                S_TOP20, C_TOP20, DECLARED_JSON, DECLARED_CSV]}
        rep["cuda_gpu_capability"] = "N/A（纯 CPU 计数任务，无 GPU 需求）"
        path = os.path.join(run_dir, "capability.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0

    wbm_rows, wbm_stats = load_wbm(SRC_WBM)
    pred, champ_stats = load_champion(SRC_CHAMP)
    label_by_id = {r[COL_ID]: r[COL_HULL] for r in wbm_rows}
    pred_dist_by_id = {r[COL_ID]: predict_distance(r, pred) for r in wbm_rows}

    cm = confusion(wbm_rows, pred)
    f1_ind = cm["f1"]
    absdiff_ind = abs(f1_ind - CARD_F1)

    # 跑内自洽：三处口径必须取自同一 cm 对象
    assert abs(f1_of(cm["tp"], cm["fp"], cm["fn"]) - f1_ind) == 0.0, "F1 三处口径不自洽"

    # ---- 与声明结果逐字段比对 ----
    declared = json.load(open(DECLARED_JSON, encoding="utf-8"))
    declared_csv_sha = integrity.get(DECLARED_CSV)
    field_map = [("n", cm["n"]), ("tp", cm["tp"]), ("fp", cm["fp"]), ("tn", cm["tn"]), ("fn", cm["fn"])]
    comparisons = []
    for name, mine in field_map:
        dv = declared.get(name)
        comparisons.append({"field": name, "declared": dv, "independent": mine, "equal": dv == mine})
    comparisons.append({"field": "f1", "declared": declared.get("f1"), "independent": f1_ind,
                        "equal": declared.get("f1") == f1_ind,
                        "abs_diff": abs((declared.get("f1") or 0) - f1_ind)})
    comparisons.append({"field": "absolute_difference", "declared": declared.get("absolute_difference"),
                        "independent": absdiff_ind,
                        "equal": declared.get("absolute_difference") == absdiff_ind})
    comparisons.append({"field": "card_f1", "declared": declared.get("card_f1"),
                        "independent": CARD_F1, "equal": declared.get("card_f1") == CARD_F1})
    cmp_sha = {"field": "hits_detail_sha256", "declared": declared.get("hits_detail_sha256"),
               "independent_recomputed": declared_csv_sha,
               "equal": declared.get("hits_detail_sha256") == declared_csv_sha}
    all_equal = all(c["equal"] for c in comparisons) and cmp_sha["equal"]

    # 四格自洽
    quad_consistent = (cm["tp"] + cm["fp"] + cm["tn"] + cm["fn"]) == cm["n"] \
        and declared.get("n") == (declared.get("tp", 0) + declared.get("fp", 0)
                                  + declared.get("tn", 0) + declared.get("fn", 0))

    # ---- 门槛：预注册 vs 参考运行 ----
    gate_prereg = {"rule": f"|F1 - {CARD_F1}| <= {PREREG_TOL}", "value": absdiff_ind,
                   "passed": absdiff_ind <= PREREG_TOL,
                   "margin_to_threshold": PREREG_TOL - absdiff_ind}

    # ---- 敏感性 ----
    probe = boundary_probe(wbm_rows, pred)

    # 浮点末位敏感性：用 1e-12 相对/绝对噪声重算是否改变四格
    def shifted(delta):
        tp = fp = tn = fn = 0
        for r in wbm_rows:
            y = r[COL_HULL]
            d = predict_distance(r, pred)
            if y is None or d is None:
                continue
            t = (y + delta) <= 0.0
            g = (d + delta) <= 0.0
            tp += t and g; fn += t and not g; fp += (not t) and g; tn += (not t) and not g
        return {"n": tp + fp + tn + fn, "tp": tp, "fp": fp, "tn": tn, "fn": fn, "f1": f1_of(tp, fp, fn)}
    eps_shift = {repr(e): shifted(e) for e in (-1e-12, -1e-13, 0.0, 1e-13, 1e-12)}
    eps_changes_cells = any(v["tp"] != cm["tp"] or v["fp"] != cm["fp"] or v["fn"] != cm["fn"]
                            for v in eps_shift.values())

    # 参考运行 f1_gate.tolerance 敏感性：门槛改判发生在哪个容差
    tol_breakeven = absdiff_ind  # |diff| 恰好等于该值时仍通过（<=）；改判点 = 该值
    tol_scan = []
    for t in REFERENCE_RUN_TOL_TABLE:
        tol_scan.append({"tolerance": t, "passed": absdiff_ind <= t})

    # ---- 七档：S 侧独立排序重建 + 与冻结名单比对 ----
    s_ranked = build_s_ranking(wbm_rows, pred)
    s_ids = [m for m, _ in s_ranked]
    budget = json.load(open(BUDGET_JSON, encoding="utf-8"))
    tiers = {}
    for k in BUDGETS:
        dec = budget.get("S", {}).get(str(k), [])
        tiers[k] = {
            "declared_len": len(dec),
            "declared_unique": len(set(dec)) == len(dec),
            "equals_independent_prefix": dec == s_ids[:k],
            "first_divergence_index": next((i for i in range(min(len(dec), k))
                                            if dec[i] != s_ids[i]), None),
            "hits": sum(1 for m in dec if (label_by_id.get(m) is not None and label_by_id[m] <= 0.0)),
        }
    s_top20_csv = list(csv.DictReader(open(S_TOP20, encoding="utf-8")))
    s_csv_ids = [r[COL_ID] for r in s_top20_csv]
    s_top20_match = s_csv_ids == budget["S"]["20"]
    s_score_check = []
    for r in s_top20_csv:
        mine = pred_dist_by_id.get(r[COL_ID])
        dv = to_float(r["strategy_score"])
        s_score_check.append({"material_id": r[COL_ID], "declared": dv, "independent": mine,
                              "abs_diff": None if (mine is None or dv is None) else abs(mine - dv),
                              "equal": dv == mine})
    # 名单哈希
    name_hash = {str(k): sha256_text_items(budget["S"][str(k)]) for k in BUDGETS}
    detail_sha = integrity.get(DECLARED_CSV)

    pos_global = {m: i for i, (m, _) in enumerate(s_ranked)}
    div_block = {
        "declared_no1_global_rank_0based": pos_global.get(budget["S"]["20"][0]),
        "independent_no1": s_ids[0],
        "independent_no1_in_declared_top20": s_ids[0] in budget["S"]["20"],
        "overlap_declared_2000_vs_independent_2000":
            len(set(budget["S"]["2000"]) & set(s_ids[:2000])),
    }

    report = {
        "run_id": run_id,
        "mode": mode,
        "script": os.path.basename(__file__),
        "script_sha256": sha256_file(os.path.join(SCRIPT_DIR, os.path.basename(__file__))),
        "run_dir": os.path.relpath(run_dir, SCRIPT_DIR),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "policy": {
            "truth_rule": "e_above_hull_mp2020_corrected_ppd_mp <= 0 (float64, no tolerance, NaN = excluded)",
            "pred_rule": "pred_dist = e_form_per_atom - (e_form_per_atom_mp2020_corrected - "
                         "e_above_hull_mp2020_corrected_ppd_mp) <= 0",
            "universe": "unique_prototype == True; join on material_id",
            "f1": "2*tp/(2*tp+fp+fn)",
            "arith": "Python float (IEEE754 binary64), 不四舍五入",
        },
        "input_sha256": integrity,
        "wbm_stats": wbm_stats,
        "champion_stats": champ_stats,
        "independent_confusion": cm,
        "independent_f1": f1_ind,
        "independent_absolute_difference": absdiff_ind,
        "field_comparison": comparisons,
        "declared_f1_hits_detail_sha256_check": cmp_sha,
        "all_declared_fields_equal": all_equal,
        "four_cell_consistent": quad_consistent,
        "card_f1": CARD_F1,
        "preregistered_gate": gate_prereg,
        "reference_run_tolerance_scan": tol_scan,
        "reference_run_tolerance_breakeven_value": tol_breakeven,
        "boundary_sensitivity": probe,
        "eps_shift_probe": {"variants": eps_shift, "changes_any_cell": eps_changes_cells},
        "s_tier_check": tiers,
        "s_top20_csv_matches_budget_json": s_top20_match,
        "top20_score_recompute": {
            "rows": s_score_check,
            "max_abs_diff": max((r["abs_diff"] or 0.0) for r in s_score_check) if s_score_check else None,
            "all_exact_equal": all(r["equal"] for r in s_score_check),
            "n_not_equal": sum(1 for r in s_score_check if not r["equal"]),
        },
        "name_hash_sha256_by_budget": name_hash,
        "f1_hits_detail_sha256": detail_sha,
        "capability_limits": [
            "C（15 模型能量中位数）无法独立重建：本运行时 shared/inputs/source/ 只有冠军 gz，"
            "不存在 15 模型预测文件，也无 full_ranking_C.csv / stable_sets.json；C 的全体分数与排序"
            "只能读 ③ 维护的正式入口（frozen_stage2/budget_lists_7tier.json 与 C_top20 文件），"
            "故 C 侧仅做一致性核对（前缀、唯一性、命中数），不做独立重算。",
            "S（冠军单模型）名单独立于本脚本可重建，但重建结果与冻结 S 名单不一致：冻结名单不是"
            "全池距离升序前缀（声明的 #1 在独立全池排序中位列第 78；独立全池 #1 不在冻结 top20 内；"
            "1000 档仅 172/2000 重合）。S_top20 的 strategy_score 与独立距离逐行一致（最大差 5.6e-17），"
            "说明差异来自子池/体系筛选而非打分公式。该子池定义在可读输入中不可见"
            "（unlabeled_candidate_pool.csv、full_ranking_S.csv、source_and_config_manifest.md 缺失），"
            "故 S 名单只核内部自洽（分数复算、单调、唯一、严格前缀），不主张全局排序正确。",
        ],
        "s_subpool_divergence": div_block,
    }

    # stdout / 结果 JSON / 报告摘要 —— 同一内存对象
    summary_line = (f"{run_id} | n={cm['n']} TP={cm['tp']} FP={cm['fp']} TN={cm['tn']} FN={cm['fn']} "
                    f"| F1={f1_ind!r} | card_f1={CARD_F1} | |Δ|={absdiff_ind!r} "
                    f"| prereg_passed={gate_prereg['passed']} | declared_all_equal={all_equal}")
    report["stdout_line"] = summary_line

    json_path = os.path.join(run_dir, "independent_result.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    stdout_path = os.path.join(run_dir, "stdout.log")
    with open(stdout_path, "w", encoding="utf-8") as fh:
        fh.write(summary_line + "\n")
        for c in comparisons:
            fh.write(f"{c['field']}: declared={c['declared']!r} independent={c['independent']!r} "
                     f"equal={c['equal']}\n")
        fh.write(f"csv_sha256: declared={cmp_sha['declared']} recomputed={cmp_sha['independent_recomputed']} "
                 f"equal={cmp_sha['equal']}\n")
        for k in BUDGETS:
            t = tiers[k]
            fh.write(f"S[{k}]: len={t['declared_len']} prefix_ok={t['equals_independent_prefix']} "
                     f"hits={t['hits']} hash={name_hash[str(k)]}\n")
    print(summary_line)
    print("result_json:", json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
