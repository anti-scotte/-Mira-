#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立复核脚本（仅 Python 标准库：gzip/csv/json/hashlib/statistics/math）。

用途
  1) 核验 raw/ 两份 gzip 的 SHA-256 与包内 SHA256SUMS.txt 一致，
     并把 results/budget_lists_7tier.json 的 SHA-256 与 results/freeze.json 登记值对照。
  2) 冠军 dpa-4.1-max-oam-pft 的程序自检：全体系 unique_prototype=True 上的四格与 F1。
  3) 只按 results/budget_lists_7tier.json 冻结的 S、C 七档有序名单逐档计数命中，
     输出两份前 20 逐行 CSV、七档合并汇总、共同/两侧独选、D20 = Hits(C) - Hits(S)。

不做的事：不写 rank_formal.py 的排序、不重排序、不重算 15 个模型的中位数、不改任何原件。
本脚本在读取 reference/ 之前完成全部计算并把结果落盘。

用法（站在「队友复验工作空间」根目录）：
  python3 outputs/recheck_champion_and_lists.py --root . --out outputs
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import statistics
import sys
import time

WBM_GZ = "raw/64706751.gz"
PRED_GZ = "raw/70836372.gz"
FREEZE = "results/freeze.json"
LISTS = "results/budget_lists_7tier.json"
SUMS = "SHA256SUMS.txt"

HULL_COL = "e_above_hull_mp2020_corrected_ppd_mp"
EFORM_MP_COL = "e_form_per_atom_mp2020_corrected"
PROTO_COL = "unique_prototype"


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_sums(path):
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            digest, name = line.split(None, 1)
            out[name.strip()] = digest.strip().lower()
    return out


def fnum(s):
    """解析成 float；空串或非有限返回 None。"""
    if s is None:
        return None
    s = s.strip()
    if s == "" or s.lower() in ("nan", "na", "none"):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v


def has_oxygen(formula):
    """含 O 且至少含一种其他元素。用正则按化学式 token 解析（不依赖 pymatgen）。"""
    import re
    if not formula:
        return False
    parts = re.findall(r"([A-Z][a-z]?)", formula)
    if not parts:
        return False
    nO = sum(1 for p in parts if p == "O")
    nOther = sum(1 for p in parts if p != "O")
    return nO >= 1 and nOther >= 1


def load_wbm(path):
    """返回 dict: material_id -> 需要的字段；同时做质量检查。"""
    rows = {}
    dup = []
    empty_hull = 0
    bad_hull = 0
    n_lines = 0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        need = {"material_id", HULL_COL, EFORM_MP_COL, PROTO_COL, "formula"}
        missing_cols = need - set(rd.fieldnames or [])
        if missing_cols:
            raise SystemExit("WBM 缺列: %s" % sorted(missing_cols))
        for r in rd:
            n_lines += 1
            mid = (r.get("material_id") or "").strip()
            if mid in rows:
                dup.append(mid)
            hull = fnum(r.get(HULL_COL))
            if (r.get(HULL_COL) or "").strip() == "":
                empty_hull += 1
            elif hull is None:
                bad_hull += 1
            rows[mid] = {
                "material_id": mid,
                "formula": (r.get("formula") or "").strip(),
                "hull": hull,
                EFORM_MP_COL: fnum(r.get(EFORM_MP_COL)),
                "proto": (r.get(PROTO_COL) or "").strip(),
            }
    return rows, {"data_rows": n_lines, "duplicate_ids": dup,
                  "empty_hull_cells": empty_hull, "nonfinite_hull_cells": bad_hull}


def load_pred(path):
    rows = {}
    dup = []
    nonfinite = 0
    bad = 0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        for r in rd:
            mid = (r.get("material_id") or "").strip()
            if mid in rows:
                dup.append(mid)
            raw = r.get("e_form_per_atom")
            v = fnum(raw)
            if v is None:
                nonfinite += 1
                try:
                    fv = float((raw or "").strip())
                    if not math.isfinite(fv):
                        bad += 1
                except Exception:
                    bad += 1
            rows[mid] = v
    return rows, {"data_rows": len(rows), "duplicate_ids": dup,
                  "missing_or_nonfinite": nonfinite}


def f1_from_counts(tp, fp, fn, tn):
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return prec, rec, f1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--card-f1", type=float, default=0.935)
    ap.add_argument("--gate", type=float, default=0.02)
    ap.add_argument("--expect-unique", type=int, default=215488)
    ap.add_argument("--expect-oxide-pool", type=int, default=23821)
    a = ap.parse_args()
    os.chdir(a.root)
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    log = []
    P = log.append

    P("=== 0) 运行环境 ===")
    P("python %s" % sys.version.replace("\n", " "))
    P("cwd %s" % os.getcwd())

    # ---------- 1) 指纹核验 ----------
    P("\n=== 1) 输入指纹核验（SHA256SUMS.txt + freeze.json）===")
    sums = read_sums(SUMS)
    P("SHA256SUMS.txt 条目数: %d" % len(sums))
    fp_rows = []
    fp_ok_all = True
    for name in (WBM_GZ, PRED_GZ, FREEZE, LISTS):
        h = sha256_file(name)
        exp = sums.get(name)
        ok = (exp == h)
        fp_ok_all &= ok
        fp_rows.append({"path": name, "measured_sha256": h,
                        "expected_sha256_sums": exp or "", "match_sums": ok})
        P("  %-40s %s  SUMS=%s  match=%s" % (name, h, exp, ok))
    # 全量 SUMS 校验（含其它文件，只读，不修改）
    allsums = []
    for name, exp in sorted(sums.items()):
        if not os.path.exists(name):
            allsums.append({"path": name, "exists": False, "match": False})
            continue
        h = sha256_file(name)
        allsums.append({"path": name, "exists": True, "match": (h == exp)})
    n_sums_ok = sum(1 for r in allsums if r.get("match"))
    P("  SUMS 全量: %d/%d 一致" % (n_sums_ok, len(allsums)))

    frz = json.load(open(FREEZE, "r", encoding="utf-8"))
    frz_entry = [f for f in frz.get("files", []) if f.get("path", "").endswith("budget_lists_7tier.json")]
    frz_exp = frz_entry[0]["sha256"] if frz_entry else None
    frz_bytes = frz_entry[0]["bytes"] if frz_entry else None
    meas = sha256_file(LISTS)
    meas_bytes = os.path.getsize(LISTS)
    P("  budget_lists_7tier.json 实测 %s (%d B)" % (meas, meas_bytes))
    P("  freeze.json 登记值        %s (%s B)" % (frz_exp, frz_bytes))
    P("  指纹一致: %s ; 字节数一致: %s" % (meas == frz_exp, meas_bytes == frz_bytes))
    P("  freeze run_id=%s version=%s champion=%s candidates=%s"
      % (frz.get("run_id"), frz.get("run_version"),
         frz.get("pool", {}).get("champion"), frz.get("pool", {}).get("candidates")))

    # ---------- 2) 读数据 + 质量检查 ----------
    P("\n=== 2) 读两份 gzip 并按 material_id 对齐（标准库 gzip/csv）===")
    wbm, wq = load_wbm(WBM_GZ)
    P("  WBM 数据行 %d, 唯一 ID %d, 重复 %d, hull 空 %d, hull 非有限 %d"
      % (wq["data_rows"], len(wbm), len(wq["duplicate_ids"]),
         wq["empty_hull_cells"], wq["nonfinite_hull_cells"]))
    pred, pq = load_pred(PRED_GZ)
    P("  预测 数据行 %d, 重复 %d, 缺失/非有限 %d"
      % (pq["data_rows"], len(pq["duplicate_ids"]), pq["missing_or_nonfinite"]))
    only_wbm = sorted(set(wbm) - set(pred))
    only_pred = sorted(set(pred) - set(wbm))
    P("  对齐: 交集 %d, WBM 独有 %d, 预测独有 %d"
      % (len(set(wbm) & set(pred)), len(only_wbm), len(only_pred)))

    # ---------- 3) 冠军 F1 程序自检（先于名单计数）----------
    P("\n=== 3) 冠军 dpa-4.1-max-oam-pft 程序自检：全体系 unique_prototype=True ===")
    uni = [m for m, r in wbm.items() if r["proto"] == "True"]
    P("  unique_prototype=True 行数: %d (预期 %d) -> %s"
      % (len(uni), a.expect_unique, len(uni) == a.expect_unique))
    tp = fp = fn = tn = 0
    skip = 0
    exact_zero = 0
    for m in uni:
        r = wbm[m]
        hull = r["hull"]
        ef_c = r[EFORM_MP_COL]
        ef_p = pred.get(m)
        if hull is None or ef_c is None or ef_p is None:
            skip += 1
            continue
        # 预测距离 = 冠军 e_form − (WBM e_form_mp2020_corrected − 原始 DFT 凸包距离)
        d = ef_p - (ef_c - hull)
        if d == 0.0:
            exact_zero += 1
        truth = hull <= 0.0
        guess = d <= 0.0
        if truth and guess:
            tp += 1
        elif not truth and guess:
            fp += 1
        elif truth and not guess:
            fn += 1
        else:
            tn += 1
    n_used = tp + fp + fn + tn
    prec, rec, f1 = f1_from_counts(tp, fp, fn, tn)
    diff = abs(f1 - a.card_f1)
    P("  参与计算 %d, 因缺失/非有限跳过 %d, 预测距离恰为 0 的行 %d" % (n_used, skip, exact_zero))
    P("  TP=%d FP=%d FN=%d TN=%d sum=%d" % (tp, fp, fn, tn, n_used))
    P("  precision=%.16f recall=%.16f" % (prec, rec))
    P("  F1=%.16f  card=%.3f  |diff|=%.16f  gate(|diff|<=%.2f)=%s margin=%.16f"
      % (f1, a.card_f1, diff, a.gate, diff <= a.gate, a.gate - diff))
    # 边界敏感性：<= / < 组合
    alt = {}
    for tk, gk in (("le", "lt"), ("lt", "lt"), ("lt", "le")):
        t = 0
        for m in uni:
            r = wbm[m]
            hull, ef_c, ef_p = r["hull"], r[EFORM_MP_COL], pred.get(m)
            if hull is None or ef_c is None or ef_p is None:
                continue
            d = ef_p - (ef_c - hull)
            truth = (hull <= 0) if tk == "le" else (hull < 0)
            guess = (d <= 0) if gk == "le" else (d < 0)
            if truth == guess:
                t += 1
        alt["truth_%s_pred_%s_agree" % (tk, gk)] = t
    P("  边界敏感性（一致数）：%s" % alt)

    # 含氧池口径核对（只读，用于口径说明）
    ox = [m for m in uni if has_oxygen(wbm[m]["formula"])]
    P("  unique_prototype=True 且含 O（含≥1种其他元素）：%d (预期 %d) -> %s"
      % (len(ox), a.expect_oxide_pool, len(ox) == a.expect_oxide_pool))

    f1_res = {"n_universe": len(uni), "n_used": n_used, "skipped": skip,
              "TP": tp, "FP": fp, "FN": fn, "TN": tn,
              "positives_truth": tp + fn, "positives_pred": tp + fp,
              "precision": prec, "recall": rec, "f1": f1,
              "card_f1": a.card_f1, "abs_diff": diff,
              "gate": "abs(F1-card)<=%.2f" % a.gate, "gate_pass": diff <= a.gate,
              "margin": a.gate - diff, "exact_zero_pred_distance": exact_zero,
              "boundary_sensitivity": alt,
              "oxide_unique_prototype_count": len(ox)}
    json.dump(f1_res, open(os.path.join(a.out, "f1_selfcheck.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    if not (diff <= a.gate):
        P("\n[STOP] F1 自检未过门槛：|diff|=%.6f > %.2f。按预注册规则 §4，先查原因，暂停解读。" % (diff, a.gate))
        open(os.path.join(a.out, "stdout.txt"), "w", encoding="utf-8").write("\n".join(log) + "\n")
        sys.exit(3)

    # ---------- 4) 冻结七档名单逐档计数 ----------
    P("\n=== 4) 只按 results/budget_lists_7tier.json 冻结有序名单逐档计数 ===")
    BL = json.load(open(LISTS, "r", encoding="utf-8"))
    budgets = BL["budgets"]
    P("  version=%s budgets=%s" % (BL.get("version"), budgets))

    # 名单结构检查
    struct = {}
    for strat in ("S", "C"):
        prev = []
        for K in budgets:
            lst = BL[strat][str(K)]
            uniq = len(set(lst)) == len(lst)
            prefix = (prev == [] or lst[:len(prev)] == prev)
            struct["%s@%d" % (strat, K)] = {"n": len(lst), "len_ok": len(lst) == K,
                                            "unique": uniq, "prefix_of_smaller": prefix}
            prev = lst
    P("  结构检查（长度/唯一/前缀嵌套）: %s" % json.dumps(struct, ensure_ascii=False))

    tier_rows = []
    for K in budgets:
        S = BL["S"][str(K)]
        C = BL["C"][str(K)]
        s_hits = c_hits = 0
        miss_ids = {"S": [], "C": []}
        for st, lst, acc in (("S", S, "s"), ("C", C, "c")):
            for mid in lst:
                r = wbm.get(mid)
                if r is None or r["hull"] is None:
                    miss_ids[st].append(mid)
                    continue
                hit = 1 if r["hull"] <= 0.0 else 0
                if st == "S":
                    s_hits += hit
                else:
                    c_hits += hit
        ss, sc = set(S), set(C)
        common = ss & sc
        s_only = ss - sc
        c_only = sc - ss
        ch = sum(1 for m in common if (wbm[m]["hull"] is not None and wbm[m]["hull"] <= 0.0))
        soh = sum(1 for m in s_only if (wbm[m]["hull"] is not None and wbm[m]["hull"] <= 0.0))
        coh = sum(1 for m in c_only if (wbm[m]["hull"] is not None and wbm[m]["hull"] <= 0.0))
        row = {"budget": K, "S_hits": s_hits, "S_rate": s_hits / len(S),
               "C_hits": c_hits, "C_rate": c_hits / len(C),
               "D_C_minus_S": c_hits - s_hits,
               "common_n": len(common), "common_hits": ch,
               "S_only_n": len(s_only), "S_only_hits": soh,
               "C_only_n": len(c_only), "C_only_hits": coh,
               "identity_ok": (c_hits - s_hits) == (coh - soh),
               "list_missing_or_nonfinite_S": len(miss_ids["S"]),
               "list_missing_or_nonfinite_C": len(miss_ids["C"]),
               "common_blindspots": len(common) - ch,
               # 原序差集（确定性：按冻结名次自上而下取差集）
               "S_only_ids_ordered": [m for m in S if m not in sc],
               "C_only_ids_ordered": [m for m in C if m not in ss]}
        tier_rows.append(row)
        P("  K=%-5d S %d/%d  C %d/%d  D=%+d  common %d(%d)  S_only %d(%d)  C_only %d(%d)  identity=%s"
          % (K, s_hits, len(S), c_hits, len(C), c_hits - s_hits, len(common), ch,
             len(s_only), soh, len(c_only), coh, row["identity_ok"]))

    with open(os.path.join(a.out, "tier_summary.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["strategy", "K", "hits", "hit_rate", "common_n", "common_hits",
                    "common_blindspots", "S_only_n", "S_only_hits", "C_only_n", "C_only_hits",
                    "hit_diff_C_minus_S", "identity_ok"])
        for r in tier_rows:
            w.writerow(["S", r["budget"], r["S_hits"], "%.6f" % r["S_rate"], r["common_n"],
                        r["common_hits"], r["common_blindspots"], r["S_only_n"], r["S_only_hits"],
                        r["C_only_n"], r["C_only_hits"], r["D_C_minus_S"], r["identity_ok"]])
            w.writerow(["C", r["budget"], r["C_hits"], "%.6f" % r["C_rate"], r["common_n"],
                        r["common_hits"], r["common_blindspots"], r["S_only_n"], r["S_only_hits"],
                        r["C_only_n"], r["C_only_hits"], r["D_C_minus_S"], r["identity_ok"]])
    json.dump(tier_rows, open(os.path.join(a.out, "tier_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 每档完整明细
    with open(os.path.join(a.out, "tier_materials.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["strategy", "budget", "rank", "material_id", "formula",
                    HULL_COL, "hit"])
        for K in budgets:
            for st in ("S", "C"):
                for i, mid in enumerate(BL[st][str(K)], 1):
                    r = wbm.get(mid, {})
                    hull = r.get("hull")
                    w.writerow([st, K, i, mid, r.get("formula", ""),
                                "" if hull is None else repr(hull),
                                1 if (hull is not None and hull <= 0.0) else 0])

    # ---------- 5) 前 20 逐行 ----------
    P("\n=== 5) 前 20 逐行（策略/名次/材料ID/原始DFT凸包距离/命中）===")
    for st in ("S", "C"):
        lst = BL[st]["20"]
        path = os.path.join(a.out, "%s_top20_scored.csv" % st)
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["strategy", "rank", "material_id", "formula",
                        "dft_hull_eV_per_atom", "hit"])
            n_hit = 0
            for i, mid in enumerate(lst, 1):
                r = wbm.get(mid, {})
                hull = r.get("hull")
                hit = 1 if (hull is not None and hull <= 0.0) else 0
                n_hit += hit
                w.writerow([st, i, mid, r.get("formula", ""),
                            "" if hull is None else repr(hull), hit])
                P("  %s %2d %-14s %-18s %14s  hit=%d"
                  % (st, i, mid, r.get("formula", ""),
                     "-" if hull is None else "%.6f" % hull, hit))
        P("  -> %s (%d/20 命中)" % (path, n_hit))

    D20 = tier_rows[0]["D_C_minus_S"]
    P("\n=== 6) 主指标 ===")
    P("  Hits@20(S) = %d ; Hits@20(C) = %d ; D20 = %+d (= C 独有命中 %d − S 独有命中 %d)"
      % (tier_rows[0]["S_hits"], tier_rows[0]["C_hits"], D20,
         tier_rows[0]["C_only_hits"], tier_rows[0]["S_only_hits"]))
    P("  K=20 S 独有 ID（原序）: %s" % tier_rows[0]["S_only_ids_ordered"])
    P("  K=20 C 独有 ID（原序）: %s" % tier_rows[0]["C_only_ids_ordered"])

    summary = {"hits20_S": tier_rows[0]["S_hits"], "hits20_C": tier_rows[0]["C_hits"],
               "D20": D20,
               "S_tiers": [r["S_hits"] for r in tier_rows],
               "C_tiers": [r["C_hits"] for r in tier_rows],
               "D_tiers": [r["D_C_minus_S"] for r in tier_rows],
               "budgets": budgets,
               "S_only_ids_20": tier_rows[0]["S_only_ids_ordered"],
               "C_only_ids_20": tier_rows[0]["C_only_ids_ordered"],
               "f1": f1_res}
    json.dump(summary, open(os.path.join(a.out, "recheck_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    fp_out = {"fingerprints": fp_rows, "sums_all_ok": n_sums_ok == len(allsums),
              "budget_lists_freeze_expected": frz_exp,
              "budget_lists_measured": meas, "match": meas == frz_exp,
              "freeze_run_id": frz.get("run_id")}
    json.dump(fp_out, open(os.path.join(a.out, "input_fingerprints.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    P("\n耗时 %.1f s" % (time.time() - t0))
    with open(os.path.join(a.out, "stdout.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
