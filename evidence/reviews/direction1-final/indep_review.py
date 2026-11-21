"""Independent review recomputation for RUN-20261121-STAGE3-02.
Written from scratch by the independent reviewer; does NOT import or reuse upstream scripts.
Steps:
 A. open the two raw gz inputs, record path/sha256/header/rows
 B. recompute champion F1 on all unique prototypes (d<=0 vs hull<=0), compare with card 0.935
 C. recompute S/C top-20 hits by material_id against frozen lists + frozen budget_lists_7tier.json
 D. recompute divergence 4 rows (rank_S, rank_C from full rankings; scores; dft distance; hit)
 E. verify identity C_hits - S_hits == onlyC_hits - onlyS_hits
 F. cross-check staged s_hits_detail.csv / c_hits_detail.csv / divergence_4rows.csv / recheck_evidence.json
"""
import gzip, csv, hashlib, json, math, os
from decimal import Decimal

ROOT = os.getcwd()
SESS = '/app/workspaces/7f145d1ba39a/projects/4e89314556/sessions'
WBM = f'{SESS}/ats-0813076ca6b206b002a21f2f84825142/scratch/raw/64706751.gz'
PRED = f'{SESS}/ats-0813076ca6b206b002a21f2f84825142/scratch/raw/70836372.gz'
FROZEN = f'{SESS}/hpp5x5x4/shared/inputs/frozen_stage2'
STORED = 'shared'

def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

out = {'inputs': {}, 'f1': {}, 'top20': {}, 'divergence': {}, 'identity': {}, 'files': {}}

# ---------- A ----------
for key, p in [('wbm_64706751', WBM), ('pred_70836372', PRED)]:
    with gzip.open(p, 'rt') as f:
        hdr = f.readline().rstrip('\n').split(',')
        n = sum(1 for _ in f)
    out['inputs'][key] = {'path': p, 'bytes': os.path.getsize(p), 'sha256': sha256(p),
                          'header': hdr, 'data_rows': n}

# ---------- B ----------
wbm = {}
with gzip.open(WBM, 'rt') as f:
    r = csv.DictReader(f)
    for row in r:
        wbm[row['material_id']] = (float(row['e_form_per_atom_mp2020_corrected']),
                                   float(row['e_above_hull_mp2020_corrected_ppd_mp']),
                                   row['formula'], row['unique_prototype'])
pred = {}
with gzip.open(PRED, 'rt') as f:
    for row in csv.DictReader(f):
        pred[row['material_id']] = float(row['e_form_per_atom'])

tp = fp = tn = fn = skipped = 0
uniq = 0
diff_bits = 0
for mid, (eform, hull, formula, uproto) in wbm.items():
    if uproto == 'True':
        uniq += 1
    if uproto != 'True':
        continue
    if mid not in pred:
        skipped += 1; continue
    pv = pred[mid]
    if not (math.isfinite(pv) and math.isfinite(eform) and math.isfinite(hull)):
        skipped += 1; continue
    d = pv - eform
    if d <= 0:
        if hull <= 0: tp += 1
        else: fp += 1
    else:
        if hull <= 0: fn += 1
        else: tn += 1
f1 = 2 * tp / (2 * tp + fp + fn)
out['f1'] = {'n': tp + fp + tn + fn, 'unique_prototype_rows': uniq, 'skipped_nonfinite_or_missing': skipped,
             'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn, 'f1': f1, 'card_f1': 0.935,
             'abs_difference': abs(f1 - 0.935), 'threshold': 0.02, 'passed': abs(f1 - 0.935) <= 0.02}

# ---------- C ----------
frozen = json.load(open(f'{FROZEN}/budget_lists_7tier.json'))
S_list = frozen['S']['20']
C_list = frozen['C']['20']

s_detail, c_detail = [], []
for i, mid in enumerate(S_list, 1):
    hull = wbm[mid][1]
    s_detail.append({'rank': i, 'material_id': mid, 'formula': wbm[mid][2],
                     'dft_hull_distance_eV_per_atom': hull,
                     'is_hit': bool(math.isfinite(hull) and hull <= 0)})
for i, mid in enumerate(C_list, 1):
    hull = wbm[mid][1]
    c_detail.append({'rank': i, 'material_id': mid, 'formula': wbm[mid][2],
                     'dft_hull_distance_eV_per_atom': hull,
                     'is_hit': bool(math.isfinite(hull) and hull <= 0)})
S_hits = sum(d['is_hit'] for d in s_detail)
C_hits = sum(d['is_hit'] for d in c_detail)
Sset, Cset = set(S_list), set(C_list)
onlyS = [m for m in S_list if m not in Cset]
onlyC = [m for m in C_list if m not in Sset]
out['top20'] = {'S': {'size': len(S_list), 'unique': len(Sset), 'hits': S_hits,
                      'miss_ids': [d['material_id'] for d in s_detail if not d['is_hit']],
                      'only_ids': onlyS, 'only_hits': sum(wbm[m][1] <= 0 for m in onlyS)},
                'C': {'size': len(C_list), 'unique': len(Cset), 'hits': C_hits,
                      'miss_ids': [d['material_id'] for d in c_detail if not d['is_hit']],
                      'only_ids': onlyC, 'only_hits': sum(wbm[m][1] <= 0 for m in onlyC)},
                'shared_count': len(Sset & Cset),
                'shared_hits': sum(wbm[m][1] <= 0 for m in (Sset & Cset)),
                'rows_S': s_detail, 'rows_C': c_detail}

# ---------- D ----------
def load_rank(path):
    rank = {}
    with open(path, newline='') as f:
        r = csv.DictReader(f)
        cols = r.fieldnames
        for i, row in enumerate(r, 1):
            mid = row['material_id']
            rank[mid] = (i, row, cols)
    return rank

FULL_RANKING_AVAILABLE = os.path.exists('scratch/full_ranking_S.csv') and os.path.exists('scratch/full_ranking_C.csv')
out['full_ranking'] = {'available': FULL_RANKING_AVAILABLE}
if FULL_RANKING_AVAILABLE:
    S_full = load_rank('scratch/full_ranking_S.csv')
    C_full = load_rank('scratch/full_ranking_C.csv')
    out['full_ranking'].update({'S_cols': S_full[next(iter(S_full))][2], 'C_cols': C_full[next(iter(C_full))][2],
                                'S_rows': len(S_full), 'C_rows': len(C_full)})

div = []
for mid in (onlyS + onlyC) if FULL_RANKING_AVAILABLE else []:
    rs, rows, _ = S_full[mid]
    rc, rowc, _ = C_full[mid]
    def getn(d, key):
        for k in d:
            if 'score' in k.lower() or k.lower() in ('d', 'c_median_score', 'strategy_score'):
                return k, d[k]
        raise KeyError(d.keys())
    ks, vs = getn(rows, 'S')
    kc, vc = getn(rowc, 'C')
    hull = wbm[mid][1]
    div.append({'material_id': mid, 'formula': wbm[mid][2], 'rank_S': rs, 'rank_C': rc,
                'score_S': vs, 'score_C': vc, 'score_S_key': ks, 'score_C_key': kc,
                'dft_hull_distance_eV_per_atom': hull,
                'is_hit': bool(math.isfinite(hull) and hull <= 0),
                'only': 'S' if mid in onlyS else 'C'})
out['divergence'] = div

# ---------- E ----------
left = C_hits - S_hits
right = out['top20']['C']['only_hits'] - out['top20']['S']['only_hits']
out['identity'] = {'S_hits': S_hits, 'C_hits': C_hits, 'left_C_minus_S': left,
                   'onlyC_hits': out['top20']['C']['only_hits'],
                   'onlyS_hits': out['top20']['S']['only_hits'], 'right_onlyC_minus_onlyS': right,
                   'verified': left == right}

# ---------- F: staged artifacts ----------
def rd(p):
    with open(p, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

st_s = rd(f'{STORED}/s_hits_detail.csv')
st_c = rd(f'{STORED}/c_hits_detail.csv')
st_d = rd(f'{STORED}/divergence_4rows.csv')
ev = json.load(open(f'{STORED}/recheck_evidence.json'))

cmp_s, cmp_c = [], []
for mine, theirs in zip(s_detail, st_s):
    diffs = {}
    if mine['material_id'] != theirs['material_id']: diffs['material_id'] = (mine['material_id'], theirs['material_id'])
    if int(theirs['rank']) != mine['rank']: diffs['rank'] = (mine['rank'], theirs['rank'])
    if theirs['formula'] != mine['formula']: diffs['formula'] = (mine['formula'], theirs['formula'])
    if float(theirs['dft_hull_distance_eV_per_atom']) != mine['dft_hull_distance_eV_per_atom']:
        diffs['dft'] = (mine['dft_hull_distance_eV_per_atom'], theirs['dft_hull_distance_eV_per_atom'])
    if (theirs['is_hit'] == 'True') != mine['is_hit']: diffs['is_hit'] = (mine['is_hit'], theirs['is_hit'])
    cmp_s.append({'material_id': mine['material_id'], 'diffs': {k: list(v) for k, v in diffs.items()}})
for mine, theirs in zip(c_detail, st_c):
    diffs = {}
    if int(theirs['rank']) != mine['rank']: diffs['rank'] = (mine['rank'], theirs['rank'])
    if theirs['material_id'] != mine['material_id']: diffs['material_id'] = (mine['material_id'], theirs['material_id'])
    if theirs['formula'] != mine['formula']: diffs['formula'] = (mine['formula'], theirs['formula'])
    if float(theirs['dft_hull_distance_eV_per_atom']) != mine['dft_hull_distance_eV_per_atom']:
        diffs['dft'] = (mine['dft_hull_distance_eV_per_atom'], theirs['dft_hull_distance_eV_per_atom'])
    if (theirs['is_hit'] == 'True') != mine['is_hit']: diffs['is_hit'] = (mine['is_hit'], theirs['is_hit'])
    cmp_c.append({'material_id': mine['material_id'], 'diffs': {k: list(v) for k, v in diffs.items()}})
cmp_d = []
for mine in div:
    theirs = next(r for r in st_d if r['material_id'] == mine['material_id'])
    diffs = {}
    if theirs['formula'] != mine['formula']: diffs['formula'] = [mine['formula'], theirs['formula']]
    if int(theirs['rank_S']) != mine['rank_S']: diffs['rank_S'] = [mine['rank_S'], int(theirs['rank_S'])]
    if int(theirs['rank_C']) != mine['rank_C']: diffs['rank_C'] = [mine['rank_C'], int(theirs['rank_C'])]
    if Decimal(theirs['score_S']) != Decimal(mine['score_S']): diffs['score_S'] = [mine['score_S'], theirs['score_S']]
    if Decimal(theirs['score_C']) != Decimal(mine['score_C']): diffs['score_C'] = [mine['score_C'], theirs['score_C']]
    if float(theirs['dft_hull_distance_eV_per_atom']) != mine['dft_hull_distance_eV_per_atom']:
        diffs['dft'] = [mine['dft_hull_distance_eV_per_atom'], theirs['dft_hull_distance_eV_per_atom']]
    if (theirs['is_hit'] == 'True') != mine['is_hit']: diffs['is_hit'] = [mine['is_hit'], theirs['is_hit']]
    if theirs['only'] != mine['only']: diffs['only'] = [mine['only'], theirs['only']]
    cmp_d.append({'material_id': mine['material_id'], 'diffs': diffs})

out['staged_check'] = {
    's_rows': len(st_s), 'c_rows': len(st_c), 'd_rows': len(st_d),
    's_diffs': [x for x in cmp_s if x['diffs']],
    'c_diffs': [x for x in cmp_c if x['diffs']],
    'd_diffs': [x for x in cmp_d if x['diffs']],
    'evidence_claims': {
        'f1': ev['f1_check']['f1'], 'n': ev['f1_check']['n'], 'abs_diff': ev['f1_check']['absolute_difference'],
        'passed': ev['f1_check']['passed'], 'S_hits': ev['top20']['summary']['S']['hits'],
        'C_hits': ev['top20']['summary']['C']['hits'], 'identity': ev['top20']['identity']['verified'],
    },
}

# ---------- precision-drift / order-sensitivity scan for the 4 divergence rows ----------
drift = []
for mine in div if FULL_RANKING_AVAILABLE else []:
    row = S_full[mine['material_id']][1]; rowc = C_full[mine['material_id']][1]
    drift.append({'material_id': mine['material_id'],
                  'staged_score_S': next(r['score_S'] for r in st_d if r['material_id'] == mine['material_id']),
                  'full_ranking_score_S': row[mine['score_S_key']],
                  'staged_score_C': next(r['score_C'] for r in st_d if r['material_id'] == mine['material_id']),
                  'full_ranking_score_C': rowc[mine['score_C_key']],
                  'ulp_S': Decimal(row[mine['score_S_key']]) - Decimal(next(r['score_S'] for r in st_d if r['material_id'] == mine['material_id'])),
                  'ulp_C': Decimal(rowc[mine['score_C_key']]) - Decimal(next(r['score_C'] for r in st_d if r['material_id'] == mine['material_id']))})
out['precision_drift'] = drift

# budget tier membership/order check: frozen tiers vs full_ranking prefixes
tier_check = []
for strat, full, col in ((('S', S_full, 'S'), ('C', C_full, 'C')) if FULL_RANKING_AVAILABLE else ()):
    order = [m for m, _ in sorted(full.items(), key=lambda kv: kv[1][0])]
    for K in frozen['budgets']:
        lst = frozen[strat][str(K)]
        tier_check.append({'strategy': strat, 'K': K, 'size': len(lst), 'unique': len(set(lst)),
                           'is_exact_prefix_of_full_ranking': lst == order[:K],
                           'mismatch_positions': sum(1 for a, b in zip(lst, order[:K]) if a != b)})
out['tier_check'] = tier_check

json.dump(out, open('scratch/indep_review.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k not in ('top20', 'divergence', 'tier_check')}, ensure_ascii=False, indent=1, default=str))
print('S hits', S_hits, 'C hits', C_hits, 'onlyS', onlyS, 'onlyC', onlyC)
print('tier all ok:', all(t['is_exact_prefix_of_full_ranking'] and t['unique'] == t['size'] for t in tier_check) if tier_check else 'N/A')
