"""Recount frozen budgets and champion F1 from two original Figshare gzip files."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("wbm", type=Path)
parser.add_argument("champion", type=Path)
args = parser.parse_args()
budget = root / "results/budget_lists_7tier.json"
for path, expected in [
    (args.wbm, "adbdd8b24086d4888195d8894c77f6d5fb29ce33bbb5d7d3898b4d79e964dc54"),
    (args.champion, "4767371b15c5169106f352e15aa13b0859e83a0f047e17cc822ff3dde42328eb"),
    (budget, "d2061c4394553b6e229555a4760296811bf82db6595b7a6d755371b0be94465c"),
]:
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"Unexpected SHA-256: {path}")

with gzip.open(args.champion, "rt", encoding="utf-8-sig") as stream:
    predictions = {}
    for row in csv.DictReader(stream):
        mid = row["material_id"]
        if mid in predictions:
            raise ValueError(f"Duplicate prediction: {mid}")
        predictions[mid] = float(row["e_form_per_atom"])

matrix = Counter()
truth = {}
with gzip.open(args.wbm, "rt", encoding="utf-8-sig") as stream:
    for row in csv.DictReader(stream):
        if row["unique_prototype"] != "True":
            continue
        mid = row["material_id"]
        d_true = float(row["e_above_hull_mp2020_corrected_ppd_mp"])
        reference = float(row["e_form_per_atom_mp2020_corrected"]) - d_true
        d_pred = predictions[mid] - reference
        if mid in truth or not all(map(math.isfinite, (d_true, d_pred))):
            raise ValueError(f"Invalid material: {mid}")
        truth[mid] = d_true <= 0
        matrix[d_pred <= 0, truth[mid]] += 1
tp, fp, tn, fn = [matrix[key] for key in [(True, True), (True, False), (False, False), (False, True)]]
f1 = 2 * tp / (2 * tp + fp + fn)
print(f"N={len(truth)} TP={tp} FP={fp} TN={tn} FN={fn} F1={f1:.10f} card=0.935 pass={abs(f1-0.935)<=0.02}")
lists = json.loads(budget.read_text(encoding="utf-8-sig"))
print("K,overlap,S_hits,C_hits,C_minus_S")
for k in (20, 50, 100, 200, 500, 1000, 2000):
    s, c = [set(lists[side][str(k)]) for side in ("S", "C")]
    if len(s) != k or len(c) != k:
        raise ValueError(f"Invalid frozen list at K={k}")
    hs, hc = sum(truth[i] for i in s), sum(truth[i] for i in c)
    print(f"{k},{len(s & c)},{hs},{hc},{hc-hs}")
