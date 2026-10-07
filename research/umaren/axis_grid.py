"""軸(指数ボーダー) × 相手(順位/指数) の馬複流し: 的中率・回収率。探索7-8月→検証9月。
レース毎に軸候補と相手候補を前計算し、条件はベクトル演算で適用する。"""
import sys, numpy as np, pandas as pd
from reverse import load

PARTNER_RULES = ([f'Ptop{n}' for n in [1, 2, 3, 4, 5]] + [f'Wtop{n}' for n in [2, 3, 4]]
                 + [f'pidx{t}' for t in [30, 40, 50, 60]] + [f'widx{t}' for t in [20, 30, 40]])


def precompute(T, H):
    Tq = T.set_index('rid'); recs = []
    cols = ['horse_no', 'P', 'W', 'place_idx', 'win_idx', 'void']
    for rid, g in H.groupby('rid', sort=False):
        X = g[cols].to_numpy(); no = X[:, 0].astype(int); P = X[:, 1].astype(int); W = X[:, 2].astype(int)
        pi = X[:, 3].astype(float); wi = X[:, 4].astype(float); vd = X[:, 5].astype(bool)
        win = {frozenset(c): a for c, a in Tq.at[rid, 'q']}
        for axis_key, rk in [('P1', P), ('W1', W)]:
            i = int(np.where(rk == 1)[0][0])
            if vd[i]: continue
            oth = np.arange(len(no)) != i
            r = dict(rid=rid, month=Tq.at[rid, 'month'], axis=axis_key, a_p=pi[i], a_w=wi[i],
                     gap=pi[i] - pi[oth].max(), wgap=wi[i] - wi[oth].max(), runners=len(no))

            def put(name, idx):
                ps = [no[j] for j in idx if not vd[j]]
                r[f'{name}_pts'] = len(ps)
                r[f'{name}_pay'] = sum(win.get(frozenset((no[i], p)), 0) for p in ps)
            oP = [j for j in np.argsort(P) if j != i]; oW = [j for j in np.argsort(W) if j != i]
            for n in [1, 2, 3, 4, 5]: put(f'Ptop{n}', oP[:n])
            for n in [2, 3, 4]: put(f'Wtop{n}', oW[:n])
            for t in [30, 40, 50, 60]: put(f'pidx{t}', [j for j in range(len(no)) if j != i and pi[j] >= t])
            for t in [20, 30, 40]: put(f'widx{t}', [j for j in range(len(no)) if j != i and wi[j] >= t])
            recs.append(r)
    return pd.DataFrame(recs)


def st(d, pts, pay):
    if len(d) == 0: return dict(races=0)
    inv = d[pts].sum() * 100
    return dict(races=len(d), pts=round(d[pts].mean(), 1), hit=round((d[pay] > 0).mean(), 3),
                roi=round(d[pay].sum() / inv, 3), roi_ex1=round((d[pay].sum() - d[pay].max()) / inv, 3))


if __name__ == '__main__':
    S = sys.argv[1]
    T, H = load(S)
    A = precompute(T, H); A.to_parquet(f'{S}/data/umaren_axis_pre.parquet')
    rows = []
    for axis in ['P1', 'W1']:
        for a_p in [0, 50, 60, 70, 80]:
            for a_w in [0, 30, 40, 50, 60]:
                for gap in [-99, 10, 20]:
                    d0 = A[(A.axis == axis) & (A.a_p >= a_p) & (A.a_w >= a_w) & (A.gap >= gap)]
                    for rl in PARTNER_RULES:
                        d = d0[(d0[f'{rl}_pts'] > 0) & (d0[f'{rl}_pts'] <= 8)]
                        for per, g in [('explore', d[d.month != '202609']), ('valid', d[d.month == '202609'])]:
                            s = st(g, f'{rl}_pts', f'{rl}_pay')
                            s.update(axis=axis, a_p=a_p, a_w=a_w, gap=gap, partner=rl, period=per); rows.append(s)
    df = pd.DataFrame(rows); df.to_csv('results_axis_grid.csv', index=False)
    print(len(df) // 2, 'specs')
