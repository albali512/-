"""Q1: does AI NAVI carry win/top2 information beyond the T-5 market?  Conditional logit, train Jul-Aug, test Sep."""
import sys, numpy as np, pandas as pd
from scipy.optimize import minimize
from common import load, horse_features
S = sys.argv[1]
R, H = load(S)
H = horse_features(H, 'T5')
H = H.merge(R[['rid', 'month']], on='rid')
H = H[~H.scr & H.p_mkt.notna() & H.p_ai.notna() & H.finish.notna() | (~H.scr & H.p_mkt.notna() & H.p_ai.notna() & (H.fstatus == '中止'))]
ok = H.groupby('rid').win.transform('sum') == 1
H = H[ok].copy()
H['lm'] = np.log(H.p_mkt); H['la'] = np.log(H.p_ai); H['lap'] = np.log(H.p_aip); H['lmp'] = np.log(H.p_mp.clip(1e-4))
H['vi'] = H.value_idx / 100; H['pi'] = H.place_idx / 100; H['wi'] = H.win_idx / 100
H['drift'] = H.drift.fillna(0).clip(-1.5, 1.5)
H['g'] = H.groupby('rid').ngroup()


def fit(df, cols, y='win'):
    X = df[cols].values; g = df.g.values; yv = df[y].values
    ng = g.max() + 1
    def nll(b):
        s = X @ b
        m = np.zeros(ng); np.maximum.at(m, g, s)
        e = np.exp(s - m[g]); den = np.bincount(g, e, ng)
        lp = s - m[g] - np.log(den[g])
        # y may have 2 ones (top2): treat as independent softmax picks (approx)
        return -(lp * yv).sum()
    r = minimize(nll, np.r_[1.0, np.zeros(len(cols) - 1)], method='BFGS')
    return r.x, r.fun


def ll(df, cols, b, y='win'):
    X = df[cols].values; g = df.g.values; s = X @ b
    d = pd.DataFrame({'g': g, 's': s, 'y': df[y].values})
    d['lse'] = d.groupby('g').s.transform(lambda v: np.log(np.exp(v - v.max()).sum()) + v.max())
    return ((d.s - d.lse) * d.y).sum()

tr = H[H.month.isin(['202607', '202608'])].copy(); te = H[H.month == '202609'].copy()
tr['g'] = tr.groupby('rid').ngroup(); te['g'] = te.groupby('rid').ngroup()
print('train races', tr.rid.nunique(), 'test races', te.rid.nunique())
for y in ['win', 'top2']:
    base = None
    for cols in [['lm'], ['la'], ['lm', 'la'], ['lm', 'la', 'lap'], ['lm', 'la', 'lap', 'vi', 'pi', 'wi'],
                 ['lm', 'lmp', 'la', 'lap'], ['lm', 'la', 'lap', 'drift'], ['lm', 'lmp', 'la', 'lap', 'drift']]:
        b, f = fit(tr, cols, y)
        l = ll(te, cols, b, y)
        if base is None: base = l
        print(y, cols, 'coef', np.round(b, 3), 'train nll %.1f' % f, 'test LL %.1f  d=%.1f' % (l, l - base))
