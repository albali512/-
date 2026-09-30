"""Rule families with race filters. Parameter chosen on explore (Jul-Aug): explore hit>=70% & races>=40, max races.
Then evaluated once on Sep."""
import sys, json, numpy as np, pandas as pd
from base import load_targets
from search import settle


def summ(d):
    d = d.dropna(subset=['hit'])
    if len(d) == 0: return dict(races=0)
    s = d.sort_values('rid'); streak = mx = 0
    for h in s.hit: streak = 0 if h else streak + 1; mx = max(mx, streak)
    return dict(races=len(d), pts=round(d.pts.mean(), 1), hit=round(d.hit.mean(), 3),
                roi=round(d.pay.sum() / (100 * d.pts.sum()), 3), med_pay=int(d[d.hit == 1].pay.median()) if d.hit.sum() else 0,
                roi_ex1=round((d.pay.sum() - d.pay.max()) / (100 * d.pts.sum()), 3), max_lose=mx)


if __name__ == '__main__':
    S = sys.argv[1]
    T, H = load_targets(S)
    D = pd.read_parquet(f'{S}/data/trio_model_eval.parquet')
    D = D[D.K == 20]
    rows, keep = [], {}
    # F1: fixed formation P3 x P6 x P6, filter runners <= N
    F1 = settle(T, H, ((3, 0), (6, 0), (6, 0))).merge(T[['rid', 'runners', 'month', 'slot']], on='rid')
    for N in [8, 9, 10, 11, 12, 16]:
        keep[('F1_P3xP6xP6', N)] = F1[F1.runners <= N]
    # F2/F3: model top-20, filter predicted coverage >= c
    for mo in ['AI', 'MKT+AI']:
        d = D[D.model == mo]
        for c in [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85]:
            keep[(f'F{2 if mo == "AI" else 3}_{mo}_top20', c)] = d[d['cov'] >= c]
    for (name, p), d in keep.items():
        for per, g in [('explore', d[d.month != '202609']), ('valid', d[d.month == '202609'])]:
            s = summ(g); s.update(rule=name, param=p, period=per); rows.append(s)
    df = pd.DataFrame(rows)
    df.to_csv(f'{S}/data/trio_rules.csv', index=False)
    pd.set_option('display.width', 220)
    w = df.pivot_table(index=['rule', 'param'], columns='period', values=['races', 'pts', 'hit', 'roi', 'roi_ex1', 'max_lose'])
    w.columns = [f'{a}_{b}' for a, b in w.columns]
    print(w[['races_explore', 'pts_explore', 'hit_explore', 'roi_explore', 'races_valid', 'pts_valid', 'hit_valid', 'roi_valid', 'roi_ex1_valid', 'max_lose_valid']].to_string())
    print('\nSelected on explore (hit>=0.70, races>=40, max races):')
    e = df[(df.period == 'explore') & (df.hit >= 0.70) & (df.races >= 40)]
    for name, g in e.groupby('rule'):
        r = g.sort_values('races', ascending=False).iloc[0]
        v = df[(df.period == 'valid') & (df.rule == name) & (df.param == r.param)].iloc[0]
        print(f'{name} param={r.param}: explore {r.races}R hit {r.hit} roi {r.roi} | Sep {v.races}R pts {v.pts} hit {v.hit} roi {v.roi} ex1 {v.roi_ex1} maxlose {v.max_lose}')
