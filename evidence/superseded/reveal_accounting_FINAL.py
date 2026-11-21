"""RUN-20261121-STAGE3-02 最终核算（F1 门槛 + 命中计数 + 自洽核对）。

F1 定义（本轮唯一口径，任务书字面 + Stage-2 冻结定义一致）：
  样本集   = WBM 全部 unique_prototype == True 的 215,488 个独特原型
  预测稳定 = 冠军 dpa-4.1-max-oam-pft 的预测凸包距离 d = e_form_per_atom − e_form_per_atom_mp2020_corrected <= 0
             （与 freeze.json protocol 的 d 定义同一式中同一参考能列）
  真值稳定 = e_above_hull_mp2020_corrected_ppd_mp <= 0
  混淆矩阵 → precision / recall / F1，与模型卡 F1 = 0.935 比较，|Δ| <= 0.02 才通过门槛

命中计数：按 material_id 一对一关联 e_above_hull_mp2020_corrected_ppd_mp，
  有限值 <= 0 eV/atom 为命中；缺失 / 重复 / 非有限值一律记错并停。
"""
import csv, gzip, hashlib, json, math, os
from pathlib import Path

SRC = Path("shared/inputs/source")
FRZ = Path("shared/inputs/frozen_stage2")
OUT = Path("scratch/stage3/out")
OUT.mkdir(parents=True, exist_ok=True)

RUN_ID = "RUN-20261121-STAGE3-02"
PREV_RUN_ID = "RUN-20261121-STAGE3-01"
CARD_F1 = 0.935
TOL = 0.02
THRESH = 0.0

EXPECT = {
    "wbm": (SRC / "2023-12-13-wbm-summary.csv.gz",
            "adbdd8b24086d4888195d8894c77f6d5fb29ce33bbb5d7d3898b4d79e964dc54", 12745623),
    "pred": (SRC / "dpa-4.1-max-oam-pft_2026-10-27-discovery.csv.gz",
             "4767371b15c5169106f352e15aa13b0859e83a0f047e17cc822ff3dde42328eb", 1315880),
    "S20": (FRZ / "S_top20_scored.csv",
            "8d0a1aee0d2e729d80f0457950ccd874516180405daa92f78dd0f2ee4466c7fa", 1259),
    "C20": (FRZ / "C_top20_signoff85f13c0c.csv",
            "85f13c0c7447b3c7aa9c2de8833841f163c196304f8c2e6f42db65fe276b178a", 686),
    "freeze": (FRZ / "freeze.json",
               "06a52898931c4704f2b90f5274dcfd5d61d9d02d4fc95b620402dfc7fb5d7347", 4348),
}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def num(s):
    try:
        x = float(s)
    except (TypeError, ValueError):
        return float("nan")
    return x


def verify():
    rows = []
    for k, (p, h, n) in EXPECT.items():
        ah, an = sha256(p), os.path.getsize(p)
        rows.append({"key": k, "path": str(p), "bytes_expected": n, "bytes_actual": an,
                     "sha256_expected": h, "sha256_actual": ah, "match": ah == h and an == n})
    frz = json.load(open(FRZ / "freeze.json"))
    total = hashlib.sha256("\n".join(sorted(f"{e['path']} {e['sha256']}" for e in frz["files"])).encode()).hexdigest()
    return rows, total


def read_top20(p):
    with open(p, newline="", encoding="utf-8") as f:
        recs = list(csv.DictReader(f))
    ids = [r["material_id"] for r in recs]
    assert len(recs) == 20 and len(set(ids)) == 20
    assert [int(r["rank"]) for r in recs] == list(range(1, 21))
    return recs


def main():
    facts = {"run_id": RUN_ID, "prev_run_id": PREV_RUN_ID,
             "run_version": "3.0.0-reveal-accounting-stage3-r2",
             "champion": "dpa-4.1-max-oam-pft"}
    vin, fp = verify()
    facts["input_verification"] = vin
    facts["freeze_total_fingerprint_expected"] = "ec146b39eba2d2281761c47cc36a2b6345b3a7cfc6e41af581401915c4b4375f"
    facts["freeze_total_fingerprint_recomputed"] = fp
    facts["inputs_all_match"] = all(r["match"] for r in vin) and fp == facts["freeze_total_fingerprint_expected"]

    S = read_top20(FRZ / "S_top20_scored.csv")
    C = read_top20(FRZ / "C_top20_signoff85f13c0c.csv")

    # ---- 单遍读 WBM：真值 + 参考能 + 化学式 + unique_prototype ----
    wbm = {}
    n_rows = n_true = n_false = n_other = 0
    hull_dup = 0
    with gzip.open(SRC / "2023-12-13-wbm-summary.csv.gz", "rt", newline="") as f:
        rd = csv.DictReader(f)
        for row in rd:
            n_rows += 1
            m = row["material_id"]
            up = row["unique_prototype"]
            if up == "True":
                n_true += 1
            elif up == "False":
                n_false += 1
            else:
                n_other += 1
            if m in wbm:
                hull_dup += 1
            wbm[m] = {"up": up, "formula": row["formula"],
                      "hull_raw": row["e_above_hull_mp2020_corrected_ppd_mp"],
                      "hull": num(row["e_above_hull_mp2020_corrected_ppd_mp"]),
                      "eform": num(row["e_form_per_atom_mp2020_corrected"]),
                      "eform_wbm": num(row["e_form_per_atom_wbm"])}

    pred = {}
    pred_dup = pred_nonfinite = 0
    with gzip.open(SRC / "dpa-4.1-max-oam-pft_2026-10-27-discovery.csv.gz", "rt", newline="") as f:
        for row in csv.DictReader(f):
            m = row["material_id"]
            if m in pred:
                pred_dup += 1
                continue
            v = num(row["e_form_per_atom"])
            if not math.isfinite(v):
                pred_nonfinite += 1
            pred[m] = v

    ids = [m for m, r in wbm.items() if r["up"] == "True"]
    missing_pred = [m for m in ids if m not in pred]
    missing_hull = [m for m in ids if not math.isfinite(wbm[m]["hull"])]
    missing_ref = [m for m in ids if not math.isfinite(wbm[m]["eform"])]

    tp = fp_ = tn = fn = skipped = 0
    for m in ids:
        w = wbm[m]
        if m not in pred or not (math.isfinite(w["hull"]) and math.isfinite(w["eform"]) and math.isfinite(pred[m])):
            skipped += 1
            continue
        d = pred[m] - w["eform"]
        ps = d <= THRESH
        ts = w["hull"] <= THRESH
        if ps and ts: tp += 1
        elif ps: fp_ += 1
        elif ts: fn += 1
        else: tn += 1
    P_ = tp / (tp + fp_) if tp + fp_ else float("nan")
    R = tp / (tp + fn) if tp + fn else float("nan")
    F1 = 2 * P_ * R / (P_ + R) if (P_ + R) else float("nan")
    facts["f1_gate"] = {
        "definition": "sample = unique_prototype==True; pred_stable = (e_form_per_atom - e_form_per_atom_mp2020_corrected)<=0; truth_stable = e_above_hull_mp2020_corrected_ppd_mp<=0",
        "wbm_rows": n_rows, "unique_prototype_true": n_true, "unique_prototype_false": n_false,
        "unique_prototype_other": n_other,
        "wbm_duplicate_material_id": hull_dup,
        "pred_rows": len(pred), "pred_duplicate_ids": pred_dup, "pred_nonfinite_eform": pred_nonfinite,
        "missing_pred_in_true_set": len(missing_pred),
        "missing_truth_hull_in_true_set": len(missing_hull),
        "missing_reference_eform_in_true_set": len(missing_ref),
        "evaluated": tp + fp_ + tn + fn, "skipped": skipped,
        "tp": tp, "fp": fp_, "tn": tn, "fn": fn,
        "precision": P_, "recall": R, "f1": F1,
        "card_f1": CARD_F1, "abs_diff": abs(F1 - CARD_F1), "tol": TOL,
        "gate_pass": bool(abs(F1 - CARD_F1) <= TOL),
    }
    facts["gate_pass"] = facts["f1_gate"]["gate_pass"]

    # ---- 命中计数 ----
    def score_list(recs, col):
        out, errs, seen = [], [], set()
        for r in recs:
            m = r["material_id"]
            if m in seen:
                errs.append({"material_id": m, "error": "duplicate_in_list"})
            seen.add(m)
            if m not in wbm:
                errs.append({"material_id": m, "error": "material_id_not_in_wbm"}); out.append({"rank": int(r["rank"]), "material_id": m, "formula": None, "score": r[col], "hull": None, "hit": None}); continue
            w = wbm[m]
            hit = None
            if not math.isfinite(w["hull"]):
                errs.append({"material_id": m, "error": f"nonfinite_or_missing_truth={w['hull_raw']!r}"})
            else:
                hit = bool(w["hull"] <= THRESH)
            out.append({"rank": int(r["rank"]), "material_id": m, "formula": w["formula"],
                        "score": r[col], "hull": w["hull"] if math.isfinite(w["hull"]) else None, "hit": hit})
        return out, errs

    s_rows, s_err = score_list(S, "strategy_score")
    c_rows, c_err = score_list(C, "C_median_score")
    facts["s_errors"], facts["c_errors"] = s_err, c_err

    s_hit = {r["material_id"] for r in s_rows if r["hit"] is True}
    c_hit = {r["material_id"] for r in c_rows if r["hit"] is True}
    only_c, only_s = sorted(c_hit - s_hit), sorted(s_hit - c_hit)
    s_ids = {r["material_id"] for r in s_rows}
    c_ids = {r["material_id"] for r in c_rows}
    facts["hits"] = {
        "S_hits": len(s_hit), "C_hits": len(c_hit), "C_minus_S": len(c_hit) - len(s_hit),
        "only_C_hit": len(only_c), "only_S_hit": len(only_s),
        "only_C_minus_only_S": len(only_c) - len(only_s),
        "only_C_hit_ids": only_c, "only_S_hit_ids": only_s,
        "identity_holds": (len(c_hit) - len(s_hit)) == (len(only_c) - len(only_s)),
        "S20_minus_C20": sorted(s_ids - c_ids), "C20_minus_S20": sorted(c_ids - s_ids),
        "S_nonhit": sorted(s_ids - s_hit), "C_nonhit": sorted(c_ids - c_hit),
    }
    facts["s_rows"], facts["c_rows"] = s_rows, c_rows

    def write(rows, p):
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["rank", "material_id", "formula", "predicted_score_eV_per_atom",
                        "dft_hull_distance_eV_per_atom", "is_hit"])
            for r in rows:
                w.writerow([r["rank"], r["material_id"], r["formula"],
                            repr(float(r["score"])),
                            "NA" if r["hull"] is None else repr(float(r["hull"])),
                            "NA" if r["hit"] is None else ("True" if r["hit"] else "False")])

    write(s_rows, OUT / "hits_s_top20.csv")
    write(c_rows, OUT / "hits_c_top20.csv")

    facts["outputs"] = {}
    for name in ("hits_s_top20.csv", "hits_c_top20.csv"):
        p = OUT / name
        facts["outputs"][name] = {"sha256": sha256(p), "bytes": os.path.getsize(p)}

    with open(OUT / "account_facts.json", "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=1)

    print(json.dumps({k: facts[k] for k in ("run_id", "inputs_all_match", "gate_pass")}, ensure_ascii=False))
    print(json.dumps(facts["f1_gate"], ensure_ascii=False, indent=1))
    print(json.dumps(facts["hits"], ensure_ascii=False, indent=1))
    print(json.dumps(facts["outputs"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
