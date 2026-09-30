"""Final: K in {15,20}, coverage filter chosen on explore; detailed OOS stats for the selected rules."""
import sys, json, numpy as np, pandas as pd
S = sys.argv[1]
D = pd.read_parquet(f'{S}/data/trio_model_eval.parquet')


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 3), round(c + h, 3)


def stats(d):
    d = d.sort_values('rid'); streak = mx = 0
    for h in d.hit: streak = 0 if h else streak + 1; mx = max(mx, streak)
    cum = (d.pay - d.pts * 100).cumsum()
    return dict(races=len(d), pts=round(d.pts.mean(), 1), hit=round(d.hit.mean(), 3), hit_ci=wilson(d.hit.sum(), len(d)),
                roi=round(d.pay.sum() / d.pts.sum() / 100, 3), roi_ex1=round((d.pay.sum() - d.pay.max()) / d.pts.sum() / 100, 3),
                med_pay=int(d[d.hit == 1].pay.median()), max_lose=mx, max_dd=int((cum.cummax() - cum).max()))


rows = []
for (mo, K), g in D.groupby(['model', 'K']):
    for c in [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]:
        x = g[g['cov'] >= c]
        for per, gg in [('explore', x[x.month != '202609']), ('valid', x[x.month == '202609'])]:
            s = stats(gg); s.update(model=mo, K=K, c=c, period=per); rows.append(s)
df = pd.DataFrame(rows); df.to_csv(f'{S}/data/trio_final_grid.csv', index=False)
sel = []
for (mo, K), g in df[(df.period == 'explore') & (df.hit >= 0.70) & (df.races >= 40)].groupby(['model', 'K']):
    r = g.sort_values('races', ascending=False).iloc[0]; sel.append((mo, K, r.c))
print('selected:', sel)
out = []
for mo, K, c in sel:
    d = D[(D.model == mo) & (D.K == K) & (D['cov'] >= c)].copy()
    d['w'] = pd.to_datetime(d.rid.str[:8]).dt.strftime('%G-W%V')
    print(f'\n=== {mo} K={K} cov>={c}')
    for per, gg in [('Jul', d[d.month == '202607']), ('Aug', d[d.month == '202608']), ('Sep(valid)', d[d.month == '202609']), ('explore', d[d.month != '202609'])]:
        print(per, stats(gg))
    v = d[d.month == '202609']
    for sl, gg in v.groupby('slot'): print('  Sep', sl, {k: stats(gg)[k] for k in ['races', 'hit', 'roi']})
    wk = d.groupby('w').apply(lambda x: pd.Series({'n': len(x), 'hit': x.hit.mean(), 'roi': x.pay.sum() / x.pts.sum() / 100}))
    print('  weekly hit min/max %.2f/%.2f  roi min/max %.2f/%.2f  weeks %d (n min %d)' % (wk.hit.min(), wk.hit.max(), wk.roi.min(), wk.roi.max(), len(wk), wk.n.min()))
    all_t = D[(D.model == mo) & (D.K == K)]
    print('  selection rate: %.2f of target races; races/weekday ~%.1f' % (len(d) / len(all_t), len(d) / d.rid.str[:8].nunique()))
    out.append(d.assign(rule=f'{mo}_K{K}_c{c}'))
pd.concat(out)[['rule', 'rid', 'slot', 'month', 'cov', 'pts', 'hit', 'pay']].to_csv(f'{S}/data/trio_selected_bets.csv', index=False)
