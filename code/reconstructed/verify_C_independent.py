"""Independent recomputation of strategy C (consensus) from unlabeled inputs.

Deliberately does NOT use any ordering-group code. Uses plain Python
`statistics.median` + `math.fsum`-free manual order-statistic to provide a
second, independent numeric path beside numpy's MedianType partition.
"""
import hashlib
import json
import math
import statistics

import numpy as np
import pandas as pd

POOL = "shared/inputs/unlabeled_candidate_pool.csv"
REF = "shared/inputs/reference_hull_energies.csv"
MAN = "shared/inputs/model_manifest.json"
CONF = "shared/inputs/02_运行配置.json"
BUDGETS_FILE = "shared/stage2_run/budgets.json"  # optional; falls back to entry_check §3

manifest = json.load(open(MAN))
conf = json.load(open(CONF))
MODELS = manifest["model_columns"]
CHAMPION = manifest["champion"]
TIE_SALT = "WBM-oxide-v1|"
report = {}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- 1. input integrity ----------
report["sha256"] = {p: sha256(p) for p in (POOL, REF, MAN, CONF)}
report["sha256_declared"] = manifest["outputs_sha256"]
report["sha256_match"] = {
    "unlabeled_candidate_pool.csv": report["sha256"][POOL]
    == manifest["outputs_sha256"]["unlabeled_candidate_pool.csv"],
    "reference_hull_energies.csv": report["sha256"][REF]
    == manifest["outputs_sha256"]["reference_hull_energies.csv"],
}

pool = pd.read_csv(POOL, dtype={"material_id": str})
ref = pd.read_csv(REF, dtype={"material_id": str})

report["pool_shape"] = list(pool.shape)
report["ref_shape"] = list(ref.shape)
report["pool_cols"] = list(pool.columns)
report["model_cols_ok"] = list(pool.columns[2:]) == MODELS
report["champion_in_models"] = CHAMPION in MODELS
report["n_unique_id_pool"] = int(pool["material_id"].nunique())
report["n_unique_id_ref"] = int(ref["material_id"].nunique())
report["id_set_equal"] = set(pool["material_id"]) == set(ref["material_id"])
report["dup_id_pool"] = int(pool["material_id"].duplicated().sum())
report["dup_id_ref"] = int(ref["material_id"].duplicated().sum())
report["null_id"] = int(pool["material_id"].isna().sum() + ref["material_id"].isna().sum())

# non-finite per model
nf = {}
for m in MODELS:
    v = pool[m].to_numpy(dtype=np.float64)
    nf[m] = {
        "nan": int(np.isnan(v).sum()),
        "posinf": int(np.isposinf(v).sum()),
        "neginf": int(np.isneginf(v).sum()),
        "nan_text": int(pool[m].astype(str).str.lower().isin(["nan", ""]).sum()),
    }
report["nonfinite_by_model"] = nf
report["ref_nonfinite"] = int((~np.isfinite(ref["e_ref"].to_numpy(dtype=np.float64))).sum())

# ---------- 2. align by material_id, compute d ----------
al = pool.merge(ref, on="material_id", how="inner", validate="one_to_one")
assert len(al) == len(pool) == len(ref)
e_ref = al["e_ref"].to_numpy(dtype=np.float64)
D = np.column_stack([al[m].to_numpy(dtype=np.float64) - e_ref for m in MODELS])
ids = al["material_id"].to_numpy()

# ---------- 3. C: numeric median over the 15 model values (path A: numpy) ----------
C_np = np.median(D, axis=1)

# independent path B: statistics.median per row (pure Python, sorts each row)
C_py = np.array([statistics.median(row) for row in D.tolist()], dtype=np.float64)
report["C_pathA_vs_pathB_maxabsdiff"] = float(np.max(np.abs(C_np - C_py)))
report["C_pathA_vs_pathB_bitwise_equal"] = bool(
    np.array_equal(C_np.view(np.int64), C_py.view(np.int64))
)
report["n_models"] = len(MODELS)
report["n_models_odd"] = len(MODELS) % 2 == 1  # odd => median is a data value, no averaging

# ---------- 4. exact tie-break key ----------
tie = np.array([hashlib.sha256(TIE_SALT.encode() + i.encode()).hexdigest() for i in ids])
order = np.lexsort((ids, tie, C_np))  # primary C asc, then hash asc, then id asc
ranked_ids = ids[order]
ranked_C = C_np[order]

# verify strict ordering property
report["sorted_ascending"] = bool(np.all(np.diff(ranked_C) >= 0))

# exact ties in C (bitwise)
u, cnt = np.unique(C_np, return_counts=True)
report["n_distinct_C_values"] = int(len(u))
report["n_exact_tie_groups"] = int((cnt > 1).sum())
report["largest_tie_group"] = int(cnt.max())

# ---------- 5. budgets ----------
try:
    budgets = json.load(open(BUDGETS_FILE))["budgets_K"]
    budgets_src = BUDGETS_FILE
except Exception:
    budgets = [20, 50, 100, 200, 500, 1000, 2000]
    budgets_src = "entry_check.md §3 (阶段1入口核验确认档位 20/50/100/200/500/1000/2000)"
report["budgets_K"] = budgets
report["budgets_source"] = budgets_src

rosters = {}
boundaries = {}
for K in budgets:
    if not (isinstance(K, int) and 1 <= K <= len(ranked_ids)):
        raise ValueError(f"invalid K {K}")
    sel_ids = ranked_ids[:K]
    sel_C = ranked_C[:K]
    rosters[K] = sel_ids
    boundaries[K] = {
        "K": K,
        "score_at_K": float(sel_C[K - 1]),
        "score_at_K_plus_1": float(ranked_C[K]) if K < len(ranked_C) else None,
        "gap": float(ranked_C[K] - sel_C[K - 1]) if K < len(ranked_C) else None,
        "distinct_ids": int(len(set(sel_ids))),
        "count": int(len(sel_ids)),
        "unique_ok": bool(len(set(sel_ids)) == K),
        "is_exact_prefix": bool(np.array_equal(sel_ids, ranked_ids[:K])),
        "tie_straddles_boundary": bool(
            K < len(ranked_C) and ranked_C[K] == sel_C[K - 1]
        ),
    }
report["budget_boundaries"] = boundaries
report["all_rosters_unique_and_sized"] = all(b["unique_ok"] for b in boundaries.values())

# ---------- 6. predicted stable set (score <= 0) ----------
stable_mask = C_np <= 0
report["stable_set"] = {
    "definition": "finite C score <= 0 (inclusive, no tolerance)",
    "count": int(stable_mask.sum()),
    "min_score": float(C_np.min()),
    "fraction": float(stable_mask.mean()),
    "n_nonfinite_C": int((~np.isfinite(C_np)).sum()),
}
# per-budget hits against PREDICTED stability (NOT DFT labels - blind)
report["predicted_stable_hits_per_budget"] = {
    K: int(stable_mask[order][:K].sum()) for K in budgets
}

# ---------- 7. archive comparison ----------
report["archive"] = {}
ARC = "shared/stage2_run/archive_C.csv"
try:
    arc = pd.read_csv(ARC, dtype={"material_id": str})
    report["archive"] = {"path": ARC, "readable": True, "shape": list(arc.shape)}
except Exception as exc:
    report["archive"] = {
        "path": ARC,
        "readable": False,
        "error": f"{type(exc).__name__}: {exc}",
    }

# ---------- 8. dump ----------
out = {
    "report": report,
    "C_scores": {i: (float(c), int(np.float64(c).view(np.int64))) for i, c in zip(ids, C_np)},
    "ranked": [{"rank": n + 1, "material_id": i, "C": float(c)} for n, (i, c) in enumerate(zip(ranked_ids, ranked_C))],
}
json.dump(out, open("scratch/check_C_result.json", "w"), ensure_ascii=False, indent=1)
pd.DataFrame(
    {
        "rank": np.arange(1, len(ranked_ids) + 1),
        "material_id": ranked_ids,
        "C_median_score": ranked_C,
    }
).to_csv("scratch/C_full_ranking_independent.csv", index=False)

print(json.dumps({k: v for k, v in report.items() if k != "budget_boundaries"}, ensure_ascii=False, indent=1))
print("\n--- boundaries ---")
print(json.dumps(boundaries, ensure_ascii=False, indent=1))
