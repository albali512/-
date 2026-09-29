"""Stage 1: fit on Jul, grid on Aug (rule selection).  Stage 2: fit on Jul+Aug, frozen rules on Sep."""
import sys, json, numpy as np, pandas as pd
from score import build, score
from strategy import select, evaluate
S = sys.argv[1]
R, H, P = build(S)
GRID = [dict(theta=t, pmin=pm, k=k, race_pmin=rp)
        for t in [1.0, 1.1, 1.2, 1.3, 1.5]
        for pm in [0.0, 0.02, 0.04, 0.06]
        for k in [3, 5, 9]
        for rp in [0.0, 0.15, 0.25]]
res = {}
for feats in ['MKT', 'MKT2', 'MKT+AI', 'MKT+AI+DRIFT']:
    for stage, tr, te in [('A', ['202607'], ['202608']), ('B', ['202607', '202608'], ['202609'])]:
        Pt, m, pr = score(H, P, tr, te, feats)
        Pt.to_parquet(f'{S}/data/scored_{stage}_{feats}.parquet')
        rows = []
        for g in GRID:
            e = evaluate(select(Pt, **g)); e.update(g); rows.append(e)
        df = pd.DataFrame(rows); df['feats'] = feats; df['stage'] = stage
        res[(feats, stage)] = df
out = pd.concat(res.values())
out.to_csv(f'{S}/data/grid_results.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
for feats in ['MKT', 'MKT2', 'MKT+AI', 'MKT+AI+DRIFT']:
    a = res[(feats, 'A')]; b = res[(feats, 'B')]
    print('=====', feats, ' Aug(stage A) summary over grid: median roi %.3f, share>1 %.2f' % (a.roi.median(), (a.roi > 1).mean()))
    print('       Sep(stage B) summary over grid: median roi %.3f, share>1 %.2f' % (b.roi.median(), (b.roi > 1).mean()))
