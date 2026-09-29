"""Per-rule stability: max losing streak, monthly & weekly ROI spread (OOS Aug+Sep)."""
import sys, numpy as np, pandas as pd
from final_eval import fam, RULES
S = sys.argv[1]
rows = []
for f in ['MKT2', 'MKT+AI']:
    for name, p in RULES.items():
        b = pd.concat([fam(pd.read_parquet(f'{S}/data/scored_{st}_{f}.parquet'), **p) for st in ['A', 'B']])
        b = b[b.void == 0]
        r = b.groupby('rid').agg(n=('hit', 'size'), h=('hit', 'max'), ret=('payout', 'sum')).reset_index().sort_values('rid')
        r['d'] = pd.to_datetime(r.rid.str[:8]); r['w'] = r.d.dt.strftime('%G-W%V'); r['m'] = r.d.dt.strftime('%Y-%m')
        streak = mx = 0
        for h in r.h: streak = 0 if h else streak + 1; mx = max(mx, streak)
        # worst drawdown in yen (100 yen/pt)
        cum = (r.ret - r.n * 100).cumsum(); dd = int((cum.cummax() - cum).max())
        wk = r.groupby('w').apply(lambda d: d.ret.sum() / d.n.sum() / 100)
        mo = r.groupby('m').apply(lambda d: d.ret.sum() / d.n.sum() / 100)
        wkn = r.groupby('w').size()
        rows.append(dict(model=f, rule=name, races=len(r), hit=round(r.h.mean(), 3), roi=round(r.ret.sum() / r.n.sum() / 100, 3),
                         max_lose_streak=mx, max_drawdown_yen=dd,
                         roi_aug=round(mo.get('2026-08', np.nan), 3), roi_sep=round(mo.get('2026-09', np.nan), 3),
                         weeks=len(wk), wk_roi_min=round(wk.min(), 3), wk_roi_max=round(wk.max(), 3), wk_roi_sd=round(wk.std(), 3),
                         weeks_gt100=int((wk > 1).sum()), wk_races_min=int(wkn.min())))
df = pd.DataFrame(rows); df.to_csv('results/stability.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
print(df.to_string())
