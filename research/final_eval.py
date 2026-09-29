"""Frozen rules (chosen on stage A = train Jul / test Aug) evaluated OOS: Aug (stage A) and Sep (stage B)."""
import sys, json, numpy as np, pandas as pd
from strategy import evaluate, day_bootstrap
S = sys.argv[1]
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)

RULES = {  # chosen on stage A only: races>=100 and hit>=35% / >=50% / >=70%, maximize Aug ROI
    'R1_top1_c30': dict(k=1, c=0.30),
    'R2_top2_c45': dict(k=2, c=0.45),
    'R3_top5_c60': dict(k=5, c=0.60),
}


def fam(Pt, k, c):
    d = Pt.sort_values(['rid', 'pm'], ascending=[True, False])
    d['r'] = d.groupby('rid').cumcount() + 1
    top = d[d.r <= k]
    cov = top.groupby('rid').pm.sum()
    return top[top.rid.isin(cov[cov >= c].index)]


def ai_baselines(Pt, H):
    """ASTRA-style AI-only rules on the same race set (no market info)."""
    out = {}
    hs = H[H.rid.isin(set(Pt.rid)) & ~H.scr]
    pr = hs.sort_values(['rid', 'place_rank', 'place_idx'], ascending=[True, True, False])
    vr = hs.sort_values(['rid', 'value_rank', 'value_idx'], ascending=[True, True, False])
    top_p = pr.groupby('rid').horse_no.apply(lambda s: list(s)[:4])
    top_v = vr.groupby('rid').horse_no.apply(lambda s: list(s)[:3])
    key = Pt.set_index(['rid', 'a', 'b'])
    def mk(pairs):
        idx = [(r, *sorted(p)) for r, ps in pairs.items() for p in ps]
        return key.reindex(idx).dropna(subset=['hit']).reset_index()
    import itertools
    out['B05_place_top4_box'] = mk({r: list(itertools.combinations(v, 2)) for r, v in top_p.items()})
    out['B04_place_top3_box'] = mk({r: list(itertools.combinations(v[:3], 2)) for r, v in top_p.items()})
    b01 = {}
    for r in top_p.index.intersection(top_v.index):
        s = set()
        for x in top_v[r]:
            for y in top_p[r][:3]:
                if x != y: s.add(tuple(sorted((x, y))))
        b01[r] = list(s)
    out['B01_value3_x_place3'] = mk(b01)
    return out


if __name__ == '__main__':
    from common import load, horse_features
    R, H = load(S); H = horse_features(H, 'T5')
    rows, allbets = [], {}
    for st, per in [('A', 'Aug'), ('B', 'Sep')]:
        for f in ['MKT', 'MKT2', 'MKT+AI']:
            Pt = pd.read_parquet(f'{S}/data/scored_{st}_{f}.parquet')
            for name, p in RULES.items():
                b = fam(Pt, **p)
                allbets.setdefault((f, name), []).append(b)
                e = evaluate(b); ci, pgt1 = day_bootstrap(b)
                e.update(period=per, model=f, rule=name, roi_ci=str(ci), p_roi_gt1=pgt1,
                         races_per_day=round(e['races'] / b.rid.str[:8].nunique(), 2)); rows.append(e)
        Pt = pd.read_parquet(f'{S}/data/scored_{st}_MKT+AI.parquet')
        for name, b in ai_baselines(Pt, H).items():
            e = evaluate(b); e.update(period=per, model='AI-only', rule=name); rows.append(e)
    for (f, name), bl in allbets.items():
        b = pd.concat(bl); e = evaluate(b); ci, pgt1 = day_bootstrap(b)
        e.update(period='Aug+Sep', model=f, rule=name, roi_ci=str(ci), p_roi_gt1=pgt1); rows.append(e)
        if f == 'MKT+AI':
            b.to_csv(f'{S}/data/bets_{name}.csv', index=False)
            vb = b.merge(R[['rid', 'venue']].rename(columns={'venue': 'v'}), on='rid')
            print(name, 'by venue (Aug+Sep OOS):')
            print(vb.groupby('v').apply(lambda d: pd.Series(evaluate(d))[['races', 'hit', 'roi']]).T.to_string())
    df = pd.DataFrame(rows)
    df.to_csv(f'{S}/data/final_eval.csv', index=False)
    cols = ['period', 'model', 'rule', 'races', 'races_per_day', 'pts', 'hit', 'exp_hit', 'roi', 'roi_ex1', 'roi_ex3', 'roi_ci', 'p_roi_gt1', 'med_hit_pay', 'maxpay']
    print(df[[c for c in cols if c in df]].to_string())
