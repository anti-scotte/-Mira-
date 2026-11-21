import gzip, csv, json, math, hashlib
BASE = '/app/workspaces/7f145d1ba39a/projects/4e89314556/sessions/ats-0813076ca6b206b002a21f2f84825142/'
WBM = BASE + 'scratch/raw/64706751.gz'
PRED = BASE + 'scratch/raw/70836372.gz'
BUD = BASE + 'shared_canonical_check/frozen_stage2/budget_lists_7tier.json'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


print('sha 64706751.gz', sha(WBM))
print('sha 70836372.gz', sha(PRED))
print('sha budget', sha(BUD))
print('sha recheck_evidence(shared)', sha('shared/recheck_evidence.json'))
for f in ['s_hits_detail.csv', 'c_hits_detail.csv', 'divergence_4rows.csv']:
    print('sha', f, sha('shared/' + f))

wbm = {}
dups = 0
with gzip.open(WBM, 'rt', newline='') as f:
    r = csv.DictReader(f)
    for row in r:
        mid = row['material_id']
        if mid in wbm:
            dups += 1
        wbm[mid] = row
print('wbm rows', len(wbm), 'dup ids', dups)


def truthy(s):
    return s.strip().lower() in ('true', '1', 't')


up_count = sum(1 for r in wbm.values() if truthy(r['unique_prototype']))
print('unique_prototype True rows', up_count)

pred = {}
pdup = 0
with gzip.open(PRED, 'rt', newline='') as f:
    r = csv.DictReader(f)
    for row in r:
        mid = row['material_id']
        if mid in pred:
            pdup += 1
        pred[mid] = float(row['e_form_per_atom'])
print('pred rows', len(pred), 'dup', pdup)

tp = fp = tn = fn = missing = nonfinite = univ = 0
for mid, row in wbm.items():
    if not truthy(row['unique_prototype']):
        continue
    univ += 1
    if mid not in pred:
        missing += 1
        continue
    eform = float(row['e_form_per_atom_mp2020_corrected'])
    hull = float(row['e_above_hull_mp2020_corrected_ppd_mp'])
    dft = eform - hull
    d = pred[mid] - dft
    if not all(map(math.isfinite, [d, dft])):
        nonfinite += 1
        continue
    stable = dft <= 0
    ps = d <= 0
    if ps and stable:
        tp += 1
    elif ps and not stable:
        fp += 1
    elif (not ps) and stable:
        fn += 1
    else:
        tn += 1
f1 = 2 * tp / (2 * tp + fp + fn)
print(dict(univ=univ, missing=missing, nonfinite=nonfinite, tp=tp, fp=fp, tn=tn, fn=fn,
           n=tp + fp + tn + fn, f1=f1, absdiff=abs(f1 - 0.935)))

bud = json.load(open(BUD))
TOP = 20
out = {}
for tag in ['S', 'C']:
    ids = bud[tag][str(TOP)]
    rows = []
    for i, mid in enumerate(ids, 1):
        w = wbm[mid]
        hull = float(w['e_above_hull_mp2020_corrected_ppd_mp'])
        eform = float(w['e_form_per_atom_mp2020_corrected'])
        dft = eform - hull
        hit = math.isfinite(dft) and dft <= 0
        rows.append(dict(rank=i, material_id=mid, formula=w['formula'], hull=hull, dft=dft, hit=hit))
    out[tag] = rows
    print(tag, 'size', len(ids), 'unique', len(set(ids)), 'hits', sum(r['hit'] for r in rows))
json.dump(out, open('artifacts/recomputed_top20.json', 'w'), ensure_ascii=False, indent=1)

for tag, f in [('S', 'shared/s_hits_detail.csv'), ('C', 'shared/c_hits_detail.csv')]:
    pub = list(csv.DictReader(open(f, encoding='utf-8-sig')))
    print('--', tag, 'published rows', len(pub), 'published hits', sum(p['is_hit'] == 'True' for p in pub))
    mism = []
    for p, r in zip(pub, out[tag]):
        if p['material_id'] != r['material_id']:
            mism.append(('id', p['material_id'], r['material_id']))
        if p['formula'] != r['formula']:
            mism.append(('formula', p['material_id'], p['formula'], r['formula']))
        if int(p['rank']) != r['rank']:
            mism.append(('rank', p['material_id']))
        if abs(float(p['dft_hull_distance_eV_per_atom']) - r['dft']) > 1e-12:
            mism.append(('dft', p['material_id'], p['dft_hull_distance_eV_per_atom'], r['dft']))
        if (p['is_hit'] == 'True') != r['hit']:
            mism.append(('hit', p['material_id']))
    print('   mismatches', mism)

S = {r['material_id'] for r in out['S']}
C = {r['material_id'] for r in out['C']}
print('only S', sorted(S - C), 'only C', sorted(C - S), 'shared', len(S & C))
