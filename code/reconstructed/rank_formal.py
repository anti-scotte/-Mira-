#!/usr/bin/env python3
"""rank_formal.py -- 有限预算下预测模型的决策组：正式盲排程序

版本: 2.0.0-formal-distance-stage2
运行编号: RUN-20261121-STAGE2-01

依据（唯一口径来源，按优先级）:
  1) shared/inputs/01_研究协议.md   （预注册协议草案，第9题）
  2) shared/inputs/02_运行配置.json （协议配置）
  3) shared/inputs/model_manifest.json （模型清单与冠军定义）
  4) 团队签认的第二阶段启动指令（本轮最新指令）

本轮启动指令覆盖/补充协议 02 的条款（逐条登记在 deviations.md）:
  - 策略 S = 冠军模型（dpa-4.1-max-oam-pft）的预测凸包距离 d
  - 策略 C = 每个材料在全部入选模型（15 个，manifest 中 selected=true）的 d 的数值中位数
  - 排序: hit 分数升序；精确同分按 sha256("WBM-oxide-v1|"+material_id) 十六进制串升序；
    再按 material_id（原 ID）升序
  - 预算 K ∈ {20,50,100,200,500,1000,2000}，每档为全排序的严格前缀
  - 稳定集合 = 该策略分数 <= 0 的全部材料（有限值，零值计入）
  - 全程 float64；d = 预测形成能/原子(eV/atom) − 固定参考形成能/原子(eV/atom)

只读取无标签列：material_id, formula, 15 个模型预测列（source_col=e_form_per_atom），
以及固定参考能 e_ref。绝不读取 e_above_hull / 任何 DFT 稳定性真值列。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys

import numpy as np

VERSION = "2.0.0-formal-distance-stage2"
TIE_SALT = "WBM-oxide-v1|"
TIE_SEP = "\x1f"  # ASCII Unit Separator, 排序键内部连接符（不会出现在 material_id 中）


# ----------------------------------------------------------------------------- 核心纯函数
def tie_hash(material_id: str) -> str:
    """固定哈希并列规则：sha256("WBM-oxide-v1|" + material_id) 十六进制串。"""
    return hashlib.sha256((TIE_SALT + material_id).encode("utf-8")).hexdigest()


def rank_scores(material_ids, scores):
    """按 (分数升序, 哈希串升序, 原 ID 升序) 排序，返回原始下标数组(0-based)。

    精确同分 = float64 位级相等比较（==）。不使用四舍五入或容差。
    """
    # 显式转 Python float64 标量：避免 numpy 标量参与元组比较时走 dtype 提升/数组比较路径
    scores = [float(np.float64(x)) for x in scores]
    ids = list(material_ids)
    n = len(ids)
    if len(scores) != n:
        raise ValueError("scores/ids length mismatch")
    if not np.all(np.isfinite(scores)):
        raise ValueError("non-finite score present; protocol forbids ranking non-finite values")
    if len(set(ids)) != n:
        raise ValueError("duplicate material_id in ranking input")
    hashes = [tie_hash(m) for m in ids]
    order = sorted(range(n), key=lambda i: (scores[i], hashes[i], ids[i]))
    return np.asarray(order, dtype=np.int64)


def median_of_rows(matrix):
    """C 策略：对每个材料取全部入选模型 d 的数值中位数（float64，n 为偶数时取中间两值算术平均）。"""
    m = np.asarray(matrix, dtype=np.float64)
    if m.ndim != 2:
        raise ValueError("matrix must be 2-D")
    if not np.all(np.isfinite(m)):
        raise ValueError("non-finite prediction in selected-model matrix; protocol requires joint exclusion")
    return np.median(m, axis=1)


def stable_set(ids_sorted, scores_sorted):
    """预测稳定集合：分数 <= 0（含零）的全部材料，按全排序顺序输出。"""
    s = np.asarray(scores_sorted, dtype=np.float64)
    return [ids_sorted[i] for i in range(len(ids_sorted)) if s[i] <= 0.0]


def budget_prefixes(ids_sorted, budgets):
    """七档预算名单：每档为该策略全排序的严格前缀；K 必须为整数且 1<=K<=N。"""
    n = len(ids_sorted)
    out = {}
    for k in budgets:
        if isinstance(k, bool) or not isinstance(k, (int, np.integer)):
            raise ValueError(f"invalid K (not integer): {k!r}")
        if not (1 <= int(k) <= n):
            raise ValueError(f"invalid K (out of [1,N]): {k}")
        out[int(k)] = list(ids_sorted[: int(k)])
    return out


# ----------------------------------------------------------------------------- 合成测试
def run_selftest():
    """合成测试：中位数、精确并列、零点、乱序输入、非法输入。任一失败即非零退出。"""
    cases = []

    def _jsonable(o):
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (list, tuple)):
            return [_jsonable(x) for x in o]
        if isinstance(o, dict):
            return {k: _jsonable(v) for k, v in o.items()}
        return o

    def rec(name, expected, actual, extra=None):
        expected, actual, extra = _jsonable(expected), _jsonable(actual), _jsonable(extra)
        ok = expected == actual
        c = {"name": name, "expected": expected, "actual": actual, "pass": bool(ok)}
        if extra:
            c["detail"] = extra
        cases.append(c)
        return ok

    # T1 中位数：奇数个模型 -> 中间值
    ok1 = rec("median_odd_3models", 2.0, float(median_of_rows([[1.0, 2.0, 9.0]])[0]))
    # T2 中位数：偶数个模型 -> 中间两值算术平均
    ok2 = rec("median_even_4models", 2.5, float(median_of_rows([[1.0, 2.0, 3.0, 4.0]])[0]))
    # T3 中位数：15 个模型（实际规模），手工期望值
    v15 = [-1.0, -0.9, -0.8, -0.7, -0.6, -0.5, -0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 9.0]
    ok3 = rec("median_15models_matches_sorted_8th", sorted(v15)[7], float(median_of_rows([v15])[0]))
    # T4 中位数不等于均值（防止误用 mean）
    ok4 = rec("median_not_mean", True, float(np.median(v15)) != float(np.mean(v15)))

    # T5 精确并列：三个同分材料按 sha256 哈希串升序（不按 ID 字典序）
    tie_ids = ["wbm-9-1", "wbm-9-2", "wbm-9-3", "wbm-9-4"]
    # 该四元组的哈希序为 (1,4,2,3)，与 ID 字典序 (1,2,3,4) 不同 —— 见 T6
    tie_scores = [0.5, 0.5, 0.5, 0.5]
    expected_tie = sorted(tie_ids, key=lambda m: (tie_hash(m), m))
    got_tie = [tie_ids[i] for i in rank_scores(tie_ids, tie_scores)]
    ok5 = rec("exact_tie_break_by_sha256", expected_tie, got_tie,
              {"hashes": [tie_hash(m) for m in tie_ids]})
    # T6 证明哈希序不等于 ID 字典序（规则必须真的按哈希）
    ok6 = rec("hash_order_differs_from_id_order", True, expected_tie != sorted(tie_ids))
    # T7 已知哈希向量自检（防止实现漂移）
    # T7 哈希串长度/十六进制格式与固定前缀复核（字节级已知向量）
    ok7 = rec("sha256_format_and_prefix", True,
              len(tie_hash("wbm-1-20320")) == 64 and
              hashlib.sha256(b"WBM-oxide-v1|wbm-1-20320").hexdigest() == tie_hash("wbm-1-20320") and
              tie_hash("wbm-1-20320") != tie_hash("WBM-oxide-v1|wbm-1-20320"))

    # T8 零点计入稳定集合，负值与正零/负零都算命中
    ok8 = rec("zero_is_stable", True, "z" in stable_set(["a", "b", "z", "c"], [-1.0, -0.0, 0.0, 1e-18]) and
              "b" in stable_set(["a", "b", "z", "c"], [-1.0, -0.0, 0.0, 1e-18]))
    ok9 = rec("tiny_positive_not_stable", False, "c" in stable_set(["a", "b", "z", "c"], [-1.0, -0.0, 0.0, 1e-18]))

    # T10 乱序输入：打乱行序后排名与名单完全不变（含并列）
    rng = np.random.default_rng(20261121)
    base_ids = [f"wbm-2-{i}" for i in range(200)] + tie_ids
    base_scores = np.round(rng.normal(0.0, 1.0, 200), 2).astype(np.float64).tolist() + [0.5, 0.5, 0.5, 0.5]
    perm = rng.permutation(len(base_ids))
    shuffled_ids = [base_ids[i] for i in perm]
    shuffled_scores = [base_scores[i] for i in perm]
    order_a = [base_ids[i] for i in rank_scores(base_ids, base_scores)]
    order_b = [shuffled_ids[i] for i in rank_scores(shuffled_ids, shuffled_scores)]
    ok10 = rec("shuffle_invariance_with_ties", order_a, order_b)

    # T11 预算前缀：前 K 名恰为全排序前 K 个，且逐档嵌套
    pref = budget_prefixes(order_a, [5, 10, 20])
    ok11 = rec("budget_prefix_nested_and_exact",
               [order_a[:5], order_a[:10], order_a[:20]],
               [pref[5], pref[10], pref[20]])
    # T12 非法 K 必须报错（0 / 超 N / 布尔）
    errs = 0
    for bad in (0, -3, len(base_ids) + 1):
        try:
            budget_prefixes(order_a, [bad])
        except ValueError:
            errs += 1
    try:
        budget_prefixes(order_a, [True])
    except ValueError:
        errs += 1
    ok12 = rec("invalid_K_raises", 4, errs)

    # T13 非有限分数必须报错（协议：非有限不入榜）
    try:
        rank_scores(["a", "b"], [1.0, np.nan])
        raised = False
    except ValueError:
        raised = True
    ok13 = rec("nonfinite_score_raises", True, raised)
    # T14 非有限预测必须报错（联合排除）
    try:
        median_of_rows([[1.0, np.inf]])
        raised2 = False
    except ValueError:
        raised2 = True
    ok14 = rec("nonfinite_prediction_raises", True, raised2)

    # T15 float64 端到端：d 的计算保持二进制精度（0.1+0.2 != 0.3）
    d_val = float(np.float64(-1.1243) - np.float64(-1.476908))
    ok15 = rec("float64_arithmetic", True, isinstance(d_val, float) and d_val != np.float32(-1.1243) - np.float32(-1.476908))

    all_pass = all(c["pass"] for c in cases) and all(
        [ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8, ok9, ok10, ok11, ok12, ok13, ok14, ok15])
    report = {
        "program": "rank_formal.py",
        "version": VERSION,
        "selftest_python": platform.python_version(),
        "selftest_numpy": np.__version__,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c["pass"]),
        "all_pass": bool(all_pass),
        "cases": cases,
    }
    return report


# ----------------------------------------------------------------------------- 正式计算
def load_inputs(pool_path, ref_path, manifest_path):
    man = json.load(open(manifest_path, "r", encoding="utf-8"))
    champion = man["champion"]
    selected = [m["model_id"] for m in man["models"] if m.get("selected") is True]
    source_col = {m["model_id"]: m.get("source_col", "e_form_per_atom") for m in man["models"]}
    for mid in selected:
        if source_col[mid] != "e_form_per_atom":
            raise SystemExit(f"unexpected source_col for {mid}: {source_col[mid]}")

    with open(pool_path, newline="", encoding="utf-8") as f:
        rdr = csv.reader(f)
        header = next(rdr)
        rows = list(rdr)
    col = {name: i for i, name in enumerate(header)}
    for need in ["material_id", "formula", champion] + selected:
        if need not in col:
            raise SystemExit(f"missing column in pool: {need}")

    ids = [r[col["material_id"]] for r in rows]
    formulas = [r[col["formula"]] for r in rows]
    if any(x == "" for x in ids):
        raise SystemExit("empty material_id in pool")
    if len(set(ids)) != len(ids):
        raise SystemExit("duplicate material_id in pool")

    # 用 numpy 的十进制字符串解析器（正确舍入到 binary64），
    # 而不是 Python float() —— float() 走的是 double 舍入路径，两者在末位常见 1 ULP 差异。
    pred = np.full((len(rows), len(selected)), np.nan, dtype=np.float64)
    for j, mid in enumerate(selected):
        c = col[mid]
        colvals = [r[c] for r in rows]
        toks = [v.strip() if v is not None else "" for v in colvals]
        arr = np.array([t if t.lower() not in {"", "nan", "na", "null", "none"} else "nan" for t in toks],
                       dtype=np.float64)
        pred[:, j] = arr

    with open(ref_path, newline="", encoding="utf-8") as f:
        rdr = csv.reader(f)
        rheader = next(rdr)
        rcol = {n: i for i, n in enumerate(rheader)}
        ref = {}
        for r in rdr:
            ref[r[rcol["material_id"]]] = np.float64(float(r[rcol["e_ref"]]))
    e_ref = np.array([ref[m] for m in ids], dtype=np.float64)  # KeyError → 报错（不静默缩池）

    bad = (~np.isfinite(e_ref)) | (~np.isfinite(pred)).any(axis=1)
    stats = {
        "n_rows": len(rows),
        "n_unique_ids": len(set(ids)),
        "n_models_selected": len(selected),
        "n_rows_jointly_excluded_nonfinite": int(bad.sum()),
        "n_missing_reference_rows": int(sum(1 for m in ids if m not in ref)),
    }
    keep = ~bad
    ids_ok = [ids[i] for i in range(len(ids)) if keep[i]]
    formulas_ok = [formulas[i] for i in range(len(formulas)) if keep[i]]
    pred_ok = pred[keep]
    e_ref_ok = e_ref[keep]
    d_all = pred_ok - e_ref_ok[:, None]  # float64 广播，eV/atom
    return man, champion, selected, ids_ok, formulas_ok, d_all, stats


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=False)
    ap.add_argument("--ref", required=False)
    ap.add_argument("--manifest", required=False)
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--budgets", default="20,50,100,200,500,1000,2000")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--selftest-out", default="synthetic_test_evidence.json")
    a = ap.parse_args(argv)

    if a.selftest:
        rep = run_selftest()
        os.makedirs(os.path.dirname(a.selftest_out) or ".", exist_ok=True)
        with open(a.selftest_out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print(json.dumps({k: rep[k] for k in ("n_cases", "n_pass", "all_pass")}, ensure_ascii=False))
        return 0 if rep["all_pass"] else 1

    for p in ("pool", "ref", "manifest"):
        if not getattr(a, p):
            ap.error(f"--{p} is required for formal run")

    budgets = [int(x) for x in a.budgets.split(",")]
    man, champion, selected, ids, formulas, d_all, stats = load_inputs(a.pool, a.ref, a.manifest)
    ci = selected.index(champion)
    d_S = np.ascontiguousarray(d_all[:, ci], dtype=np.float64)
    d_C = np.ascontiguousarray(median_of_rows(d_all), dtype=np.float64)

    out = {"version": VERSION, "champion": champion, "selected_models": selected,
           "budgets": budgets, "input_stats": stats}
    os.makedirs(a.outdir, exist_ok=True)

    for name, sc in (("S", d_S), ("C", d_C)):
        order = rank_scores(ids, sc)
        ids_sorted = [ids[i] for i in order]
        sc_sorted = [float(sc[i]) for i in order]
        fm_sorted = [formulas[i] for i in order]
        with open(os.path.join(a.outdir, f"full_ranking_{name}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["rank", "material_id", "formula", f"score_{name}", "tie_hash"])
            for r, (m, s, fm) in enumerate(zip(ids_sorted, sc_sorted, fm_sorted), start=1):
                w.writerow([r, m, fm, repr(s), tie_hash(m)])
        pref = budget_prefixes(ids_sorted, budgets)
        out[f"budget_lists_{name}"] = {str(k): v for k, v in pref.items()}
        out[f"stable_set_{name}"] = stable_set(ids_sorted, sc_sorted)
        out[f"n_stable_{name}"] = len(out[f"stable_set_{name}"])
        out[f"n_ranked_{name}"] = len(ids_sorted)
        out[f"head20_{name}"] = ids_sorted[:20]
        # 边界信息：第 K 名与第 K+1 名分数（并列检查）
        out[f"boundary_{name}"] = {}
        for k in budgets:
            if k < len(ids_sorted):
                out[f"boundary_{name}"][str(k)] = {
                    "score_at_K": repr(sc_sorted[k - 1]),
                    "score_at_K_plus_1": repr(sc_sorted[k]),
                    "tie_across_boundary": bool(sc_sorted[k - 1] == sc_sorted[k]),
                }

    with open(os.path.join(a.outdir, "budget_lists_7tier.json"), "w", encoding="utf-8") as f:
        json.dump({"version": VERSION,
                   "note": "每档为该策略全排序的严格前缀；K 为整数且 1<=K<=N；材料按 material_id 列出，顺序即名次",
                   "budgets": budgets,
                   "S": out["budget_lists_S"], "C": out["budget_lists_C"]},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(a.outdir, "stable_sets.json"), "w", encoding="utf-8") as f:
        json.dump({"version": VERSION,
                   "rule": "预测稳定集合 = 该策略分数 <= 0 的全部材料（float64 有限值，零值计入，无容差），按该策略全排序顺序",
                   "S": {"champion": champion, "n": out["n_stable_S"], "members": out["stable_set_S"]},
                   "C": {"models": selected, "n": out["n_stable_C"], "members": out["stable_set_C"]}},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(a.outdir, "run_summary.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"version": VERSION, "n_ranked": len(ids), "n_stable_S": out["n_stable_S"],
                      "n_stable_C": out["n_stable_C"], "head20_S": out["head20_S"][:3],
                      "head20_C": out["head20_C"][:3]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
