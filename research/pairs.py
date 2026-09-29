"""Build pair-level table: market pair prob at T-x (Harville on win odds, exacta-derived), final quinella odds, outcome."""
import sys, numpy as np, pandas as pd
from common import load, horse_features, quinella_hits, harville_pairs
S = sys.argv[1]
R, H = load(S)
H = horse_features(H, 'T5')
H3 = horse_features(pd.read_parquet(f'{S}/data/horses.parquet').query('rid in @R.rid'), 'T3')[['rid', 'horse_no', 'p_mkt']].rename(columns={'p_mkt': 'p_mkt3'})
H = H.merge(H3, on=['rid', 'horse_no'], how='left')
QF = pd.read_parquet(f'{S}/data/quinella_final.parquet')
EX = pd.read_parquet(f'{S}/data/exacta_ts.parquet')
hits = quinella_hits(R)


def ipf_quinella(P, g, t='T5', iters=200):
    """Quinella pair shares at T-x: seed = Harville(win odds); rows scaled (symmetric IPF) so that
    each horse's total involvement equals its quinella-pool share 2*vote_rate at T-x."""
    v = g[f'quinella_vote_rate_{t}'].values.astype(float)
    if np.isnan(v).any() or v.sum() <= 0:
        return np.full_like(P, np.nan)
    x = np.maximum(2 * v / v.sum(), 1e-4)
    Q = P + 1e-9
    np.fill_diagonal(Q, 0)
    for _ in range(iters):
        f = np.sqrt(x / Q.sum(1))
        Q = Q * f[:, None] * f[None, :]
    return Q / np.triu(Q, 1).sum()


rows = []
for rid, g in H.groupby('rid'):
    g = g[~g.scr]
    if g.p_mkt.isna().any() or len(g) < 5: continue
    nos = g.horse_no.values; P = harville_pairs(g.p_mkt.values)
    P3 = harville_pairs(g.p_mkt3.values) if g.p_mkt3.notna().all() else np.full_like(P, np.nan)
    hit = {k: v for k, v in hits[rid]}
    PQ = ipf_quinella(P, g, 'T5')
    PQ3 = ipf_quinella(P3 if not np.isnan(P3).all() else P, g, 'T3')
    for i in range(len(nos)):
        for j in range(i + 1, len(nos)):
            a, b = sorted((int(nos[i]), int(nos[j])))
            fs = frozenset((a, b))
            rows.append((rid, a, b, P[i, j], P3[i, j], PQ[i, j], PQ3[i, j], int(fs in hit), hit.get(fs, 0)))
Pp = pd.DataFrame(rows, columns=['rid', 'a', 'b', 'ph5', 'ph3', 'pq5', 'pq3', 'hit', 'payout'])
Pp = Pp.merge(QF, on=['rid', 'a', 'b'], how='left')
for t in ['T5', 'T3', 'T10', 'FINAL']:
    e1 = EX[['rid', 'first_no', 'second_no', f'ex_{t}']].rename(columns={'first_no': 'a', 'second_no': 'b', f'ex_{t}': 'x1'})
    e2 = EX[['rid', 'first_no', 'second_no', f'ex_{t}']].rename(columns={'first_no': 'b', 'second_no': 'a', f'ex_{t}': 'x2'})
    Pp = Pp.merge(e1, on=['rid', 'a', 'b'], how='left').merge(e2, on=['rid', 'a', 'b'], how='left')
    Pp[f'pex_{t}'] = 0.75 / Pp.x1 + 0.75 / Pp.x2  # both directions needed
    Pp = Pp.drop(columns=['x1', 'x2'])
Pp = Pp.merge(R[['rid', 'month', 'venue']], on='rid')
Pp.to_parquet(f'{S}/data/pairs.parquet')
print(len(Pp), Pp.rid.nunique(), 'races; hits', Pp.hit.sum())
print('coverage final qodds', Pp.qodds_final.notna().mean(), 'pex_T5', Pp.pex_T5.notna().mean())
