"""Model-based trio: Plackett-Luce top-3 on AI NAVI features (fit on ALL races of the train period),
buy the top-K most probable triples per race; race selection by predicted coverage."""
import sys, json, itertools, numpy as np, pandas as pd
from scipy.optimize import minimize

AI_FEATS = ['la', 'lap', 'pi', 'vi']       # AI only (morning-available)
MKT_FEATS = ['lm', 'lmp', 'la', 'lap']     # + T-5 market (comparison)


def feats(H):
    H = H.copy()
    def norm_inv(col):
        q = 1 / H[col].where(H[col] > 0)
        return q / q.groupby(H.rid).transform('sum')
    H['la'] = np.log(norm_inv('fair_win')); H['lap'] = np.log(norm_inv('fair_place'))
    H['pi'] = H.place_idx / 100; H['vi'] = H.value_idx / 100
    if 'win_odds_T5' in H:
        H['lm'] = np.log(norm_inv('win_odds_T5')); H['lmp'] = np.log(norm_inv('place_odds_T5').clip(1e-4))
    return H


class PL3:
    def __init__(self, cols): self.cols = cols

    def fit(self, H):
        races = []
        for rid, g in H.groupby('rid'):
            f = g.finish.values
            idx = [np.where(f == k)[0] for k in (1, 2, 3)]
            if any(len(i) != 1 for i in idx) or g[self.cols].isna().any().any(): continue
            races.append((g[self.cols].values, [i[0] for i in idx]))
        k = len(self.cols)
        def nll(th):
            b, lam = th[:k], th[k]; tot = 0.0
            for X, (i, j, l) in races:
                s = X @ b; s -= s.max(); lp = s - np.log(np.exp(s).sum())
                s2 = lam * lp
                m = np.ones(len(s), bool); m[i] = False
                tot += lp[i] + s2[j] - np.log(np.exp(s2[m]).sum())
                m[j] = False
                tot += s2[l] - np.log(np.exp(s2[m]).sum())
            return -tot
        r = minimize(nll, np.r_[1.0, np.zeros(k - 1), 0.8], method='L-BFGS-B')
        self.b, self.lam = r.x[:k], r.x[k]; return self

    def triples(self, g):
        s = g[self.cols].values @ self.b; s -= s.max(); p = np.exp(s) / np.exp(s).sum(); q = p ** self.lam
        nos = g.horse_no.values; n = len(p); out = {}
        for i, j, l in itertools.permutations(range(n), 3):
            pr = p[i] * q[j] / (q.sum() - q[i]) * q[l] / (q.sum() - q[i] - q[j])
            key = tuple(sorted((nos[i], nos[j], nos[l])))
            out[key] = out.get(key, 0) + pr
        return sorted(out.items(), key=lambda x: -x[1])
