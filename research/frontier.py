"""Hit-rate oriented families: top-k pairs by model prob, optional per-pair edge filter & race concentration filter."""
import sys, numpy as np, pandas as pd
from strategy import evaluate
S = sys.argv[1]
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)


def fam(Pt, k, e=0.0, c=0.0, omax=None, rank_by='pm'):
    d = Pt.copy()
    d['edge'] = d.pm / (0.775 / d.odds_est)
    d = d.sort_values(['rid', rank_by], ascending=[True, False])
    d['r'] = d.groupby('rid').cumcount() + 1
    top = d[d.r <= k]
    cov = top.groupby('rid').pm.sum()
    top = top[top.rid.isin(cov[cov >= c].index)]
    top = top[top.edge >= e]
    if omax: top = top[top.odds_est <= omax]
    return top


rows = []
for st in ['A', 'B']:
    Pt = pd.read_parquet(f'{S}/data/scored_{st}_MKT+AI.parquet')
    for k in [1, 2, 3, 5, 9]:
        for e in [0, 1.0, 1.1, 1.2, 1.3]:
            for c in [0, 0.3, 0.45, 0.6]:
                r = evaluate(fam(Pt, k, e, c)); r.update(stage=st, k=k, e=e, c=c); rows.append(r)
df = pd.DataFrame(rows)
df.to_csv(f'{S}/data/frontier.csv', index=False)
w = df.pivot_table(index=['k', 'e', 'c'], columns='stage', values=['races', 'hit', 'roi', 'roi_ex1'])
w.columns = [f'{a}_{b}' for a, b in w.columns]
w = w[['races_A', 'hit_A', 'roi_A', 'roi_ex1_A', 'races_B', 'hit_B', 'roi_B', 'roi_ex1_B']]
print(w.round(3).to_string())
