"""Unified ranking CLI 1.0.0: python rank.py INPUT_DIR CONFIG_JSON > result.json"""
import csv, hashlib, json, math, sys
from pathlib import Path
from statistics import median

def table(path, fields):
    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        if next(reader) != ['material_id', *fields]: raise ValueError('invalid header')
        out = {}
        for mid, *values in reader:
            if not mid or mid in out or len(values) != len(fields): raise ValueError('invalid row')
            out[mid] = list(map(float, values))
            if not all(map(math.isfinite, out[mid])): raise ValueError('nonfinite input')
        return out

def rank(root, config):
    models = config['models']; champ = models.index(config['champion']); ks = config['budgets']
    if not models or len(set(models)) != len(models): raise ValueError('invalid models')
    pool = table(root/'pool.csv', []); ref = table(root/'ref_hull.csv', ['e_ref']); pred = table(root/'predictions.csv', models)
    if not pool.keys() == ref.keys() == pred.keys(): raise ValueError('ID mismatch')
    if any(type(k) != int or not 1 <= k <= len(pool) for k in ks): raise ValueError('budget outside pool')
    scores = {'S': {}, 'C': {}}
    for i in pool:
        ds = [x-ref[i][0] for x in pred[i]]; scores['S'][i] = ds[champ]; scores['C'][i] = median(ds)
        if not all(map(math.isfinite, [*ds, scores['C'][i]])): raise ValueError('nonfinite score')
    result = {}
    for name, score in scores.items():
        ids = sorted(pool, key=lambda i: (score[i], hashlib.sha256(('WBM-oxide-v1|'+i).encode()).hexdigest(), i))
        result[name] = dict(order=ids, scores=[score[i] for i in ids], top={str(k): ids[:k] for k in ks}, nonpositive=[i for i in ids if score[i] <= 0])
    return result

if __name__ == '__main__':
    print(json.dumps(rank(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))), allow_nan=False))
