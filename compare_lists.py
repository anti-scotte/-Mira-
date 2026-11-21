"""Compare the published S and C shortlists for a given budget."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", type=Path, default=Path(__file__).parent / "data" / "node_4_budget_lists.json")
parser.add_argument("--k", default="20")
args = parser.parse_args()
with args.input.open(encoding="utf-8-sig") as stream:
    budgets = json.load(stream)["lists"]
key = args.k
if key not in budgets:
    parser.error("Available budgets: " + ", ".join(budgets))
lists = budgets[key]
single, consensus = (set(lists[name]) for name in ("S", "C"))
for name in ("S", "C"):
    ids = lists[name]
    if len(ids) != int(key) or len(set(ids)) != int(key):
        raise ValueError(f"Invalid shortlist length or duplicate IDs in {name}")
print(json.dumps({
    "K": int(key), "overlap": len(single & consensus),
    "only_S": sorted(single - consensus), "only_C": sorted(consensus - single),
}, indent=2))
