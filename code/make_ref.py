import pandas as pd
import numpy as np
from sys import argv
key='material_id'
a='e_form_per_atom_mp2020_corrected'
b='e_above_hull_mp2020_corrected_ppd_mp'
ids=pd.read_csv(argv[2],usecols=[key])[key]
v=pd.read_csv(argv[1],usecols=[key,a,b],float_precision='round_trip').set_index(key,verify_integrity=True).loc[ids]
h=(v[a]-v[b]).rename('e_ref')
assert np.isfinite(h).all() and ids.is_unique
h.to_csv(argv[3])
back=pd.read_csv(argv[3],float_precision='round_trip').set_index(key)
assert back.index.equals(h.index) and np.array_equal(back.e_ref,h)
assert back.e_ref.iloc[0]==float(v.iloc[0][a])-float(v.iloc[0][b])
