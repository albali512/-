"""Shared loaders / feature builders for the AI NAVI quinella research."""
import json
import numpy as np, pandas as pd

TAKE_Q = 0.775  # NAR quinella payout rate (approx.)


def load(S):
    R = pd.read_parquet(f'{S}/data/races.parquet')
    H = pd.read_parquet(f'{S}/data/horses.parquet')
    R = R[R.has_result & (R.n_quinella > 0)].copy()
    H = H[H.rid.isin(set(R.rid))].copy()
    R['month'] = R.date.str[:6]
    return R, H


def horse_features(H, t='T5'):
    """Per-horse PIT features. Only T-x market data + AI NAVI (fixed pre-race)."""
    H = H.copy()
    # PIT: a horse is a non-runner only if it has no odds at T-x. Later scratches/exclusions are
    # kept in the model and their tickets are refunded at settlement ('void').
    H['void'] = H.scratched.fillna(False).astype(bool)
    H['scr'] = ~(H[f'win_odds_{t}'] > 0)
    live = ~H.scr
    wo = H[f'win_odds_{t}'].where(live)
    H['q_mkt'] = (1 / wo).where(wo > 0)
    H['p_mkt'] = H.q_mkt / H.groupby('rid').q_mkt.transform('sum')
    fw = H.fair_win.where(live)
    H['q_ai'] = (1 / fw).where(fw > 0)
    H['p_ai'] = H.q_ai / H.groupby('rid').q_ai.transform('sum')
    fp = H.fair_place.where(live)
    H['q_aip'] = (1 / fp).where(fp > 0)
    H['p_aip'] = H.q_aip / H.groupby('rid').q_aip.transform('sum')
    po = H[f'place_odds_{t}'].where(live)
    H['q_mp'] = (1 / po).where(po > 0)
    H['p_mp'] = H.q_mp / H.groupby('rid').q_mp.transform('sum')
    H['n_live'] = H.groupby('rid').scr.transform(lambda s: (~s).sum())
    H['mkt_rank'] = H.groupby('rid').p_mkt.rank(ascending=False, method='first')
    H['drift'] = np.log(H[f'win_odds_{t}'] / H['win_odds_T30'])
    H['top2'] = (H.finish <= 2).astype(int)
    H['win'] = (H.finish == 1).astype(int)
    return H


def quinella_hits(R):
    """dict rid -> list of (frozenset pair, payout per 100 yen)."""
    return {r.rid: [(frozenset(c), a) for c, a in json.loads(r.quinella)] for r in R.itertuples()}


def harville_pairs(p):
    """p: array of win probs (sum 1). Return matrix P[i,j] quinella prob (symmetric)."""
    p = np.asarray(p, float)
    n = len(p)
    P = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j and p[i] < 1 and p[j] < 1:
                P[i, j] = p[i] * p[j] / (1 - p[i]) + p[j] * p[i] / (1 - p[j])
    return P
