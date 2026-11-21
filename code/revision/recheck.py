"""从项目原始压缩文件和第二阶段名单独立核算，仅写入本修订目录。"""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

out = Path(__file__).resolve().parent
root = out.parent
wbm = root / "64706751.gz"
pred = next(root.rglob("70836372.gz"))
run = root / "Mira产物" / "有限预算下S与C命中对比-l8dpcu47"
budget = next(run.rglob("budget_lists_7tier.json"))
lists = json.loads(budget.read_text(encoding="utf-8-sig"))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert digest(wbm) == "adbdd8b24086d4888195d8894c77f6d5fb29ce33bbb5d7d3898b4d79e964dc54"
assert digest(pred) == "4767371b15c5169106f352e15aa13b0859e83a0f047e17cc822ff3dde42328eb"
with gzip.open(pred, "rt", encoding="utf-8-sig") as f:
    predictions = {}
    for row in csv.DictReader(f):
        mid = row["material_id"]
        assert mid not in predictions
        predictions[mid] = float(row["e_form_per_atom"])

truth = {}
tp = fp = tn = fn = 0
with gzip.open(wbm, "rt", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        if row["unique_prototype"] != "True":
            continue
        mid = row["material_id"]
        assert mid not in truth
        distance = float(row["e_above_hull_mp2020_corrected_ppd_mp"])
        reference = float(row["e_form_per_atom_mp2020_corrected"]) - distance
        score = predictions[mid] - reference
        assert math.isfinite(score) and math.isfinite(distance)
        positive, stable = score <= 0, distance <= 0
        tp += positive and stable
        fp += positive and not stable
        fn += not positive and stable
        tn += not positive and not stable
        truth[mid] = distance

f1 = 2 * tp / (2 * tp + fp + fn)
assert len(truth) == 215488 and abs(f1 - 0.935) <= 0.02
sets = {}
hits = {}
for k in ("S", "C"):
    ids = lists[k]["20"]
    sets[k] = set(ids)
    assert len(ids) == len(sets[k]) == 20
    old = next(root.rglob(f"hits_{k.lower()}_top20.csv"))
    with old.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert [r["material_id"] for r in rows] == ids
    for r in rows:
        value = truth[r["material_id"]]
        assert float(r["dft_hull_distance_eV_per_atom"]) == value
        assert (r["is_hit"].lower() == "true") == (value <= 0)
    hits[k] = sum(truth[i] <= 0 for i in ids)
results = dict(n=len(truth), tp=tp, fp=fp, tn=tn, fn=fn, f1=f1, card_f1=0.935,
               absolute_difference=abs(f1-0.935), hits=hits, budget_sha256=digest(budget),
               unique_distances={k:{i:truth[i] for i in sorted(sets[k]-sets[other])}
                                 for k,other in (("S","C"),("C","S"))})
(out/"核验结果.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
print(f"F1={f1:.10f}, hits={hits}")
