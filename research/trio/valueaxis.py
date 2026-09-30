"""ROI-oriented trio formations with value-rank (期待値) top 2-3 horses as axis.  <=20 points.
Selection on explore (Jul-Aug) by ROI excluding the largest payout; validation on Sep.
Primary set = weekday main/final races; the same rules on ALL races as a robustness reference."""
import sys, json, itertools, numpy as np, pandas as pd
from base import load_targets
S = sys.argv[1]


def race_ctx(T, H):
    Hg = dict(tuple(H.groupby('rid'))); ctx = []
    for r in T.itertuples():
        g = Hg.get(r.rid)
        if g is None: continue
        ctx.append(dict(rid=r.rid, month=r.month, slot=getattr(r, 'slot', ''), n=len(g),
                        P=list(g.sort_values('P').horse_no), V=list(g.sort_values('V').horse_no),
                        pi=dict(zip(g.horse_no, g.place_idx)), P_of=dict(zip(g.horse_no, g.P)), W_of=dict(zip(g.horse_no, g.W)),
                        vr=dict(zip(g.horse_no, g.value_rank)), pr=dict(zip(g.horse_no, g.place_rank)),
                        void=set(g[g.void].horse_no), win={tuple(c): a for c, a in json.loads(r.trio)}))
    return ctx


def axis(c, k, min_pi):
    return [h for h in c['V'][:k] if c['pi'][h] >= min_pi]


def fam_A(c, k, N, min_pi):          # each axis horse, partners = place top-N (excluding itself)
    t = set()
    for a in axis(c, k, min_pi):
        part = [h for h in c['P'] if h != a][:N]
        for x, y in itertools.combinations(part, 2): t.add(tuple(sorted((a, x, y))))
    return t


def fam_B(c, k, N, min_pi):          # 2-horse axis from value top-k pairs, 3rd = place top-N
    ax = axis(c, k, min_pi); t = set()
    for a, b in itertools.combinations(ax, 2):
        third = [h for h in c['P'] if h not in (a, b)][:N]
        for z in third: t.add(tuple(sorted((a, b, z))))
    return t


def fam_C(c, k, A, B, min_pi):       # formation: col1 value top-k, col2 place top-A, col3 place top-B
    X1 = axis(c, k, min_pi); X2 = c['P'][:A]; X3 = c['P'][:B]; t = set()
    for x in X1:
        for y in X2:
            for z in X3:
                if len({x, y, z}) == 3: t.add(tuple(sorted((x, y, z))))
    return t


def fam_D(c):                        # reference: Note-Hidden BASE axis x P1-2 x P1-4 (P2-P4)
    if c['n'] < 8: return set()
    cand = [h for h in c['V'] if 3 <= c['pr'][h] <= 6 and c['pi'][h] >= 30 and c['vr'][h] <= 2 and c['W_of'][h] >= 5]
    if not cand: return set()
    a = cand[0]; t = set()
    for y in c['P'][:2]:
        for z in c['P'][:4]:
            if len({a, y, z}) == 3: t.add(tuple(sorted((a, y, z))))
    return t


SPECS = {}
for mp in [0, 30]:
    for k, N in [(1, 5), (1, 6), (2, 4), (2, 5), (3, 3), (3, 4)]:
        SPECS[f'A_axisV{k}_x_P{N}_pi{mp}'] = (lambda c, k=k, N=N, mp=mp: fam_A(c, k, N, mp))
    for k, N in [(2, 6), (2, 9), (2, 14), (3, 4), (3, 5), (3, 6)]:
        SPECS[f'B_pairV{k}_x_P{N}_pi{mp}'] = (lambda c, k=k, N=N, mp=mp: fam_B(c, k, N, mp))
    for k, A, B in [(2, 2, 5), (2, 3, 5), (2, 3, 6), (2, 4, 6), (3, 2, 4), (3, 2, 5), (3, 3, 4), (3, 3, 5)]:
        SPECS[f'C_V{k}xP{A}xP{B}_pi{mp}'] = (lambda c, k=k, A=A, B=B, mp=mp: fam_C(c, k, A, B, mp))
SPECS['D_NoteHidden_P2P4'] = fam_D


def run(ctx, fn, min_runners=0):
    out = []
    for c in ctx:
        if c['n'] < min_runners: continue
        t = fn(c)
        if not t or len(t) > 20: continue
        live = [x for x in t if not set(x) & c['void']]
        if not live: continue
        pay = sum(c['win'].get(x, 0) for x in live)
        out.append((c['rid'], c['month'], len(live), int(pay > 0), pay))
    return pd.DataFrame(out, columns=['rid', 'month', 'pts', 'hit', 'pay'])


def stats(d):
    if len(d) == 0: return dict(races=0)
    d = d.sort_values('rid'); st = mx = 0
    for h in d.hit: st = 0 if h else st + 1; mx = max(mx, st)
    top = d.pay.sort_values(ascending=False); inv = d.pts.sum() * 100
    return dict(races=len(d), pts=round(d.pts.mean(), 1), hit=round(d.hit.mean(), 3), roi=round(d.pay.sum() / inv, 3),
                roi_ex1=round((d.pay.sum() - top.iloc[0]) / inv, 3), roi_ex3=round((d.pay.sum() - top.iloc[:3].sum()) / inv, 3),
                max_lose=mx, maxpay=int(top.iloc[0]), top1_share=round(top.iloc[0] / max(d.pay.sum(), 1), 2))


def boot(d, n=3000, seed=928):
    if len(d) == 0: return None
    g = d.assign(day=d.rid.str[:8]).groupby('day').agg(st=('pts', 'sum'), ret=('pay', 'sum'))
    rng = np.random.default_rng(seed); idx = rng.integers(0, len(g), (n, len(g)))
    r = g.ret.values[idx].sum(1) / (g.st.values[idx].sum(1) * 100)
    return np.percentile(r, [2.5, 97.5]).round(2).tolist(), round((r > 1).mean(), 3)


if __name__ == '__main__':
    rows = []
    for scope in ['target', 'all']:
        T, H = load_targets(S, scope)
        ctx = race_ctx(T, H)
        for name, fn in SPECS.items():
            for mr in [0, 8]:
                d = run(ctx, fn, mr)
                for per, g in [('explore', d[d.month != '202609']), ('valid', d[d.month == '202609'])]:
                    s = stats(g); s.update(scope=scope, spec=name, min_runners=mr, period=per); rows.append(s)
        print(scope, 'races', len(ctx))
    df = pd.DataFrame(rows); df.to_csv(f'{S}/data/valueaxis_grid.csv', index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500)
    for scope in ['target', 'all']:
        x = df[df.scope == scope]
        w = x.pivot_table(index=['spec', 'min_runners'], columns='period', values=['races', 'pts', 'hit', 'roi', 'roi_ex1'])
        w.columns = [f'{a}_{b}' for a, b in w.columns]
        w = w.sort_values('roi_ex1_explore', ascending=False)
        print(f'\n===== {scope}: top 20 by explore ROI(ex max1)')
        print(w[['races_explore', 'pts_explore', 'hit_explore', 'roi_explore', 'roi_ex1_explore', 'races_valid', 'hit_valid', 'roi_valid', 'roi_ex1_valid']].head(20).to_string())
        print(f'{scope}: specs with explore ROI>1: {(w.roi_explore > 1).sum()}/{len(w)}; valid ROI>1: {(w.roi_valid > 1).sum()}/{len(w)}; median valid ROI {w.roi_valid.median():.3f}')
