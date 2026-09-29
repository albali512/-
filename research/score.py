"""Walk-forward scoring: produce pair table with model prob + PIT price for a test period, model fit on a train period."""
import sys, numpy as np, pandas as pd
from common import load, horse_features
from model import PL2, Price, FEATS, prep_h


def build(S):
    R, H = load(S)
    H = prep_h(horse_features(H, 'T5'))
    P = pd.read_parquet(f'{S}/data/pairs.parquet')
    return R, H, P


def score(H, P, train_months, test_months, feats='MKT+AI'):
    Htr = H[H.rid.isin(set(P[P.month.isin(train_months)].rid))]
    m = PL2(FEATS[feats]).fit(Htr)
    pr = Price().fit(P[P.month.isin(train_months)])
    Pt = P[P.month.isin(test_months)].copy()
    rows = []
    Hte = H[H.rid.isin(set(Pt.rid))]
    for rid, g in Hte.groupby('rid'):
        M, p = m.pair_probs(g)
        nos = g.horse_no.values
        for i in range(len(nos)):
            for j in range(i + 1, len(nos)):
                a, b = sorted((int(nos[i]), int(nos[j])))
                rows.append((rid, a, b, M[i, j]))
    pm = pd.DataFrame(rows, columns=['rid', 'a', 'b', 'pm'])
    Pt = Pt.merge(pm, on=['rid', 'a', 'b'], how='inner')
    Pt = Pt[Pt.pq5.notna()]
    Pt['odds_est'] = pr.odds(Pt)
    Pt['ev'] = Pt.pm * Pt.odds_est
    return Pt, m, pr
