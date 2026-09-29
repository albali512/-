"""Betting-rule evaluation on scored pair tables (100 yen flat per combination, max 9 points)."""
import numpy as np, pandas as pd


def select(Pt, theta=1.2, pmin=0.0, k=9, race_pmin=0.0, pmax_odds=None, min_n=0):
    d = Pt[(Pt.ev >= theta) & (Pt.pm >= pmin)]
    if pmax_odds: d = d[d.odds_est <= pmax_odds]
    d = d.sort_values(['rid', 'ev'], ascending=[True, False]).groupby('rid').head(k)
    if race_pmin > 0:
        cov = d.groupby('rid').pm.transform('sum')
        d = d[cov >= race_pmin]
    return d


def settle(bets):
    """Drop refunded tickets (a horse scratched/excluded after the decision time)."""
    return bets[bets.void == 0] if 'void' in bets else bets


def evaluate(bets, label='', days=None):
    bets = settle(bets)
    if len(bets) == 0:
        return dict(label=label, races=0)
    r = bets.groupby('rid').agg(n=('pm', 'size'), ret=('payout', 'sum'), hit=('hit', 'max'), cov=('pm', 'sum'))
    stake = r.n.sum() * 100; ret = r.ret.sum()
    top = r.ret.sort_values(ascending=False)
    out = dict(label=label, races=len(r), pts=r.n.mean().round(2), hit=r.hit.mean().round(3),
               roi=round(ret / stake, 3), roi_ex1=round((ret - top.iloc[0]) / stake, 3),
               roi_ex3=round((ret - top.iloc[:3].sum()) / stake, 3), exp_hit=round(r['cov'].mean(), 3),
               profit=int(ret - stake), maxpay=int(top.iloc[0]))
    hp = bets[bets.hit == 1].payout
    out['med_hit_pay'] = int(hp.median()) if len(hp) else 0
    return out


def day_bootstrap(bets, n=5000, seed=928):
    rng = np.random.default_rng(seed)
    bets = settle(bets)
    b = bets.assign(day=bets.rid.str[:8])
    g = b.groupby('day').agg(st=('pm', 'size'), ret=('payout', 'sum'))
    st, ret = g.st.values * 100, g.ret.values
    idx = rng.integers(0, len(g), (n, len(g)))
    rois = ret[idx].sum(1) / st[idx].sum(1)
    return np.percentile(rois, [2.5, 50, 97.5]).round(3), (rois > 1).mean().round(3)
