"""Fit the MKT+AI pair model on Jul+Aug and save frozen parameters (v1.0) for live use."""
import sys, json
from score import build
from model import PL2, FEATS
S = sys.argv[1]
R, H, P = build(S)
tr = set(P[P.month.isin(['202607', '202608'])].rid)
m = PL2(FEATS['MKT+AI']).fit(H[H.rid.isin(tr)])
json.dump({'version': 'v1.0', 'train': '2026-07-15..2026-08-31', 'features': FEATS['MKT+AI'],
           'b': [round(float(x), 6) for x in m.b], 'lam': round(float(m.lam), 6), 'odds_time': 'T-5',
           'rules': {'R1_top1_c30': {'k': 1, 'c': 0.30}, 'R2_top2_c45': {'k': 2, 'c': 0.45}, 'R3_top5_c60': {'k': 5, 'c': 0.60}}},
          open('params_v1.json', 'w'), ensure_ascii=False, indent=1)
print(open('params_v1.json').read())
