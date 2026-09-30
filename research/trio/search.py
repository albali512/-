"""Formation search on explore period (Jul-Aug); pre-race AI features only.  Column sets = top-a by place (P) U top-b by value (V)."""
import sys, json, itertools, numpy as np, pandas as pd
from base import load_targets
S = sys.argv[1]


def colset(g, a, b):
    return set(g[g.P <= a].horse_no) | set(g[g.V <= b].horse_no)


def tickets(g, spec):
    (a1, b1), (a2, b2), (a3, b3) = spec
    X1, X2, X3 = colset(g, a1, b1), colset(g, a2, b2), colset(g, a3, b3)
    t = set()
    for x in X1:
        for y in X2:
            for z in X3:
                if len({x, y, z}) == 3: t.add(tuple(sorted((x, y, z))))
    return t


def settle(T, H, spec, maxpts=20):
    out = []
    Hg = dict(tuple(H.groupby('rid')))
    for r in T.itertuples():
        g = Hg[r.rid]; t = tickets(g, spec)
        if len(t) > maxpts or len(t) == 0: out.append((r.rid, len(t), np.nan, np.nan)); continue
        void = set(g[g.void].horse_no)
        t = {x for x in t if not (set(x) & void)}
        win = {tuple(c): a for c, a in json.loads(r.trio)}
        pay = sum(win.get(x, 0) for x in t)
        out.append((r.rid, len(t), int(pay > 0), pay))
    return pd.DataFrame(out, columns=['rid', 'pts', 'hit', 'pay'])


def summ(d):
    d = d.dropna()
    if len(d) == 0: return dict(races=0)
    return dict(races=len(d), pts=round(d.pts.mean(), 1), hit=round(d.hit.mean(), 3), roi=round(d.pay.sum() / (100 * d.pts.sum()), 3))


if __name__ == '__main__':
    T, H = load_targets(S)
    E = T[T.month.isin(['202607', '202608'])]
    specs = []
    # nested place-only formations
    for a1 in [1, 2, 3]:
        for a2 in range(a1, 8):
            for a3 in range(a2, 11):
                specs.append(((a1, 0), (a2, 0), (a3, 0)))
    # add value horses to columns 2/3 (value = 穴 candidates)
    for a1 in [1, 2]:
        for a2 in [2, 3, 4]:
            for a3 in [4, 5, 6]:
                for b2 in [0, 1, 2]:
                    for b3 in [1, 2, 3]:
                        if a3 >= a2 >= a1: specs.append(((a1, 0), (a2, b2), (a3, b3)))
    # value axis
    for b1 in [1, 2]:
        for a2 in [2, 3, 4]:
            for a3 in [4, 5, 6, 7]:
                specs.append(((0, b1), (a2, b1), (a3, b1)))
    rows = []
    for sp in specs:
        # quick point count check on a sample race of 12 runners: skip specs above 20 everywhere
        d = settle(E, H, sp)
        if d.hit.notna().mean() < 0.8: continue
        s = summ(d); s.update(spec=str(sp), coverage=round(d.hit.notna().mean(), 3)); rows.append(s)
    df = pd.DataFrame(rows).sort_values('hit', ascending=False)
    df.to_csv(f'{S}/data/trio_search_explore.csv', index=False)
    pd.set_option('display.width', 200)
    print(len(df), 'specs within 20 pts'); print(df.head(25).to_string(index=False))
