"""Simple (hand-usable) race filters for fixed place-rank formations: concentration of AI place index in the top-6."""
import sys, numpy as np, pandas as pd
from base import load_targets
from search import settle
from select_eval import summ
S = sys.argv[1]
T, H = load_targets(S)
g = H.groupby('rid')
pi = H.assign(pp=H.place_idx.clip(lower=0))
top6 = pi[pi.P <= 6].groupby('rid').pp.sum(); allp = pi.groupby('rid').pp.sum()
p6 = pi[pi.P == 6].set_index('rid').place_idx; p7 = pi[pi.P == 7].set_index('rid').place_idx
feat = pd.DataFrame({'share6': top6 / allp, 'gap67': (p6 - p7).fillna(99)})
rows = []
for spec_name, spec in [('P3xP6xP6', ((3, 0), (6, 0), (6, 0))), ('BOX6', ((6, 0), (6, 0), (6, 0))), ('P2xP6xP7', ((2, 0), (6, 0), (7, 0)))]:
    d = settle(T, H, spec).merge(T[['rid', 'runners', 'month']], on='rid').merge(feat, left_on='rid', right_index=True)
    for f, grid in [('share6', [0.6, 0.65, 0.7, 0.75, 0.8, 0.85]), ('gap67', [2, 4, 6, 8, 10])]:
        for th in grid:
            x = d[d[f] >= th]
            for per, gg in [('explore', x[x.month != '202609']), ('valid', x[x.month == '202609'])]:
                s = summ(gg); s.update(spec=spec_name, filt=f, th=th, period=per); rows.append(s)
df = pd.DataFrame(rows); df.to_csv(f'{S}/data/trio_simple.csv', index=False)
w = df.pivot_table(index=['spec', 'filt', 'th'], columns='period', values=['races', 'pts', 'hit', 'roi'])
w.columns = [f'{a}_{b}' for a, b in w.columns]
pd.set_option('display.width', 220)
print(w[['races_explore', 'pts_explore', 'hit_explore', 'roi_explore', 'races_valid', 'pts_valid', 'hit_valid', 'roi_valid']].to_string())
print('\nSelected on explore (hit>=0.70, races>=40, max races):')
e = df[(df.period == 'explore') & (df.hit >= 0.70) & (df.races >= 40)]
for (sp, f), gq in e.groupby(['spec', 'filt']):
    r = gq.sort_values('races', ascending=False).iloc[0]
    v = df[(df.period == 'valid') & (df.spec == sp) & (df.filt == f) & (df.th == r.th)].iloc[0]
    print(f'{sp} {f}>={r.th}: explore {r.races}R hit {r.hit} roi {r.roi} | Sep {v.races}R pts {v.pts} hit {v.hit} roi {v.roi} maxlose {v.max_lose}')
