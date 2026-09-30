"""Cross-fit Jul<->Aug for selection data, Jul+Aug -> Sep for validation.  Top-K triples per race."""
import sys, json, numpy as np, pandas as pd
from base import load_targets
from model_trio import PL3, feats, AI_FEATS, MKT_FEATS
S = sys.argv[1] if len(sys.argv) > 1 else "."
T, _ = load_targets(S)
HA = pd.read_parquet(f'{S}/data/horses.parquet')
R = pd.read_parquet(f'{S}/data/races.parquet'); R['month'] = R.date.str[:6]
HA = HA.merge(R[['rid', 'month', 'has_result']], on='rid')
HA = HA[HA.has_result & ~HA.fstatus.eq('取消') & HA.fair_win.notna() & HA.fair_place.notna()]
HA['void'] = HA.fstatus.eq('除外')
HA = feats(HA)


def score(train_months, test_rids, cols):
    tr = HA[HA.month.isin(train_months) & ~HA.void]
    m = PL3(cols).fit(tr)
    rows = []
    for rid, g in HA[HA.rid.isin(test_rids)].groupby('rid'):
        if g[cols].isna().any().any(): continue
        tri = m.triples(g)
        rows.append((rid, tri, set(g[g.void].horse_no)))
    return m, rows


def evaluate(rows, K):
    out = []
    Tr = T.set_index('rid')
    for rid, tri, void in rows:
        buy = [t for t, p in tri[:K]]; cov = sum(p for t, p in tri[:K])
        live = [t for t in buy if not set(t) & void]
        win = {tuple(c): a for c, a in json.loads(Tr.loc[rid, 'trio'])}
        pay = sum(win.get(t, 0) for t in live)
        out.append(dict(rid=rid, cov=cov, pts=len(live), hit=int(pay > 0), pay=pay,
                        runners=len(set(x for t, _ in tri for x in t)), slot=Tr.loc[rid, 'slot'], month=Tr.loc[rid, 'month'],
                        top1p=tri[0][1]))
    return pd.DataFrame(out)


if __name__ == '__main__':
    res = {}
    for name, cols in [('AI', AI_FEATS), ('MKT+AI', MKT_FEATS)]:
        parts = []
        for trm, tem in [(['202608'], '202607'), (['202607'], '202608'), (['202607', '202608'], '202609')]:
            m, rows = score(trm, set(T[T.month == tem].rid), cols)
            print(name, 'train', trm, 'b', np.round(m.b, 3), 'lam %.3f' % m.lam, 'test', tem, len(rows))
            for K in [15, 20]:
                d = evaluate(rows, K); d['K'] = K; d['model'] = name; parts.append(d)
        res[name] = pd.concat(parts)
    D = pd.concat(res.values()); D.to_parquet(f'{S}/data/trio_model_eval.parquet')
    for (mo, K), g in D.groupby(['model', 'K']):
        for per, gg in [('explore(JulAug)', g[g.month != '202609']), ('valid(Sep)', g[g.month == '202609'])]:
            print(f'{mo:7s} K={K} {per:16s} races {len(gg)} pred_cov {gg["cov"].mean():.3f} hit {gg.hit.mean():.3f} roi {gg.pay.sum()/gg.pts.sum()/100:.3f}')
