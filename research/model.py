"""Pair-probability model: Plackett-Luce (top-2) on horse strengths from market(T-5) + AI NAVI.
   Price model: log(final quinella odds) from T-5 market info (PIT)."""
import numpy as np, pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import LinearRegression

FEATS = {
    'MKT': ['lm'],
    'MKT2': ['lm', 'lmp'],
    'MKT+AI': ['lm', 'lmp', 'la', 'lap'],
    'MKT+AI+DRIFT': ['lm', 'lmp', 'la', 'lap', 'drift'],
}


def prep_h(H):
    H = H[~H.scr & H.p_mkt.notna() & H.p_ai.notna()].copy()
    H['lm'] = np.log(H.p_mkt); H['la'] = np.log(H.p_ai); H['lap'] = np.log(H.p_aip)
    H['lmp'] = np.log(H.p_mp.fillna(H.p_mkt).clip(1e-4))
    H['drift'] = H.drift.fillna(0).clip(-1.5, 1.5)
    return H


class PL2:
    """P(i 1st, j 2nd) = p_i * p_j^lam / sum_{k!=i} p_k^lam ; p = softmax(Xb)."""
    def __init__(self, cols): self.cols = cols

    def _race_arrays(self, H):
        out = []
        for rid, g in H.groupby('rid', sort=False):
            X = g[self.cols].values
            f = g.finish.values
            i1 = np.where(f == 1)[0]; i2 = np.where(f == 2)[0]
            out.append((rid, X, g.horse_no.values, i1, i2))
        return out

    def fit(self, H):
        races = [r for r in self._race_arrays(H) if len(r[3]) == 1 and len(r[4]) >= 1]
        k = len(self.cols)
        def nll(th):
            b, lam = th[:k], th[k]
            tot = 0.0
            for _, X, _, i1, i2 in races:
                s = X @ b; s = s - s.max()
                lp = s - np.log(np.exp(s).sum())
                i = i1[0]; j = i2[0]
                s2 = lam * lp; m = np.ones(len(s2), bool); m[i] = False
                mx = s2[m].max()
                tot += lp[i] + s2[j] - (mx + np.log(np.exp(s2[m] - mx).sum()))
            return -tot
        th0 = np.r_[1.0, np.zeros(k - 1), 0.8]
        r = minimize(nll, th0, method='L-BFGS-B')
        self.b, self.lam = r.x[:k], r.x[k]
        return self

    def pair_probs(self, g):
        s = g[self.cols].values @ self.b; s = s - s.max()
        p = np.exp(s) / np.exp(s).sum()
        pl = p ** self.lam
        n = len(p); P = np.zeros((n, n))
        tot = pl.sum()
        for i in range(n):
            P[i] += p[i] * pl / (tot - pl[i])
        P[np.arange(n), np.arange(n)] = 0
        return P + P.T, p


def price_feats(d, t='5'):
    """PIT price features at T-t: IPF quinella share (all pairs) + exacta-derived share (popular pairs)."""
    lq = np.log(0.775 / d[f'pq{t}'].clip(1e-7))
    has = d[f'pex_T{t}'].notna().astype(float)
    lx = np.log(0.775 / d[f'pex_T{t}']).fillna(0)
    return pd.DataFrame({'lq': lq, 'lq2': lq ** 2, 'has': has, 'lxq': (lx - lq) * has})


class Price:
    """Predict log(payout/100 | hit) from PIT info: fit log(final qodds) then shrink by mean hit bias on train."""
    def __init__(self, t='5'): self.t = t

    def fit(self, P):
        d = P[(P.qodds_final > 0) & P[f'pq{self.t}'].notna()]
        self.lr = LinearRegression().fit(price_feats(d, self.t), np.log(d.qodds_final))
        h = d[d.hit == 1]
        self.bias = float((np.log(h.payout / 100) - self.lr.predict(price_feats(h, self.t))).mean())
        return self

    def odds(self, P):
        return np.exp(self.lr.predict(price_feats(P, self.t)) + self.bias)
