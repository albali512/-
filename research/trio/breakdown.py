"""Venue / region breakdown (hit rate, ROI, split explore Jul-Aug vs Sep) for the trio rules and the quinella R2.
Target = weekday main/final races; ALL = every race (reference, larger n)."""
import sys, json, numpy as np, pandas as pd
from base import load_targets
from valueaxis import race_ctx, run, SPECS
from model_trio import PL3, feats, AI_FEATS
S = sys.argv[1]
NANKAN = {'大井', '川崎', '船橋', '浦和'}
REGION = {'大井': '南関東', '川崎': '南関東', '船橋': '南関東', '浦和': '南関東',
          '門別': '北海道・東北', '盛岡': '北海道・東北', '水沢': '北海道・東北',
          '名古屋': '東海・北陸', '笠松': '東海・北陸', '金沢': '東海・北陸',
          '園田': '西日本', '高知': '西日本', '佐賀': '西日本'}


def t20_all(T):
    """AI-only PL3 top-20 triples, cross-fit (Jul<-Aug, Aug<-Jul, Sep<-Jul+Aug), for every race in T."""
    HA = pd.read_parquet(f'{S}/data/horses.parquet')
    R = pd.read_parquet(f'{S}/data/races.parquet'); R['month'] = R.date.str[:6]
    HA = HA.merge(R[['rid', 'month', 'has_result']], on='rid')
    HA = HA[HA.has_result & ~HA.fstatus.eq('取消') & HA.fair_win.notna() & HA.fair_place.notna()]
    HA['void'] = HA.fstatus.eq('除外'); HA = feats(HA)
    trio = T.set_index('rid').trio; out = []
    for trm, tem in [(['202608'], '202607'), (['202607'], '202608'), (['202607', '202608'], '202609')]:
        m = PL3(AI_FEATS).fit(HA[HA.month.isin(trm) & ~HA.void])
        for rid, g in HA[HA.rid.isin(set(T[T.month == tem].rid))].groupby('rid'):
            if g[AI_FEATS].isna().any().any() or len(g) < 4: continue
            tri = m.triples(g)[:20]; cov = sum(p for _, p in tri)
            void = set(g[g.void].horse_no); live = [t for t, _ in tri if not set(t) & void]
            win = {tuple(c): a for c, a in json.loads(trio[rid])}
            pay = sum(win.get(t, 0) for t in live)
            out.append((rid, tem, len(live), int(pay > 0), pay, cov))
    return pd.DataFrame(out, columns=['rid', 'month', 'pts', 'hit', 'pay', 'cov'])


def agg(d):
    if len(d) == 0: return pd.Series(dtype=float)
    inv = d.pts.sum() * 100; top = d.pay.max()
    e, v = d[d.month != '202609'], d[d.month == '202609']
    f = lambda x: round(x.pay.sum() / (x.pts.sum() * 100), 3) if len(x) else np.nan
    return pd.Series({'races': len(d), 'hit': round(d.hit.mean(), 3), 'roi': round(d.pay.sum() / inv, 3),
                      'roi_ex1': round((d.pay.sum() - top) / inv, 3),
                      'R_JulAug': len(e), 'roi_JulAug': f(e), 'hit_JulAug': round(e.hit.mean(), 3) if len(e) else np.nan,
                      'R_Sep': len(v), 'roi_Sep': f(v), 'hit_Sep': round(v.hit.mean(), 3) if len(v) else np.nan})


rows = []
for scope in ['target', 'all']:
    T, H = load_targets(S, scope)
    venue = T.set_index('rid').venue
    ctx = race_ctx(T, H)
    strat = {
        'T20_AI_top20_cov55': None, 'AI_top20_nofilter': None,
        'P3xP6xP6': lambda c: SPECS['C_V2xP2xP5_pi0'] and __import__('valueaxis').fam_C(c, 0, 0, 0, 0) if False else None,
    }
    D = {}
    t = t20_all(T)
    D['T20 (AI上位20点, 予測的中≥55%)'] = t[t['cov'] >= 0.55]
    D['AI上位20点 (絞り込みなし)'] = t
    import valueaxis as va
    D['複勝3頭×6頭×6頭'] = run(ctx, lambda c: {tuple(sorted((x, y, z))) for x in c['P'][:3] for y in c['P'][:6] for z in c['P'][:6] if len({x, y, z}) == 3}, 0)
    D['期待値上位2→複勝上位2→複勝上位5'] = run(ctx, SPECS['C_V2xP2xP5_pi0'], 0)
    D['期待値上位2頭軸→複勝上位5流し'] = run(ctx, SPECS['A_axisV2_x_P5_pi0'], 0)
    D['Note-Hidden×P2-P4'] = run(ctx, SPECS['D_NoteHidden_P2P4'], 0)
    for name, d in D.items():
        d = d.assign(venue=d.rid.map(venue))
        d['group'] = np.where(d.venue.isin(NANKAN), '南関', 'その他'); d['region'] = d.venue.map(REGION)
        for lvl in ['group', 'region', 'venue']:
            for k, g in d.groupby(lvl):
                s = agg(g); s['scope'] = scope; s['strategy'] = name; s['level'] = lvl; s['key'] = k; rows.append(s)
        s = agg(d); s['scope'] = scope; s['strategy'] = name; s['level'] = 'total'; s['key'] = '全体'; rows.append(s)
    print(scope, 'done')
# quinella R2 (T-5 market + AI) by venue, OOS Aug+Sep
b = pd.read_csv('../results/bets_R2_top2_c45.csv'); b = b[b.void == 0]
r = b.groupby('rid').agg(pts=('hit', 'size'), hit=('hit', 'max'), pay=('payout', 'sum')).reset_index()
r['month'] = r.rid.str[:6]; r['venue'] = r.rid.str.split('_').str[1]
r['group'] = np.where(r.venue.isin(NANKAN), '南関', 'その他'); r['region'] = r.venue.map(REGION)
for lvl in ['group', 'region', 'venue']:
    for k, g in r.groupby(lvl):
        s = agg(g); s['scope'] = 'all(8-9月OOS)'; s['strategy'] = '馬複R2'; s['level'] = lvl; s['key'] = k; rows.append(s)
df = pd.DataFrame(rows)
df.to_csv('results/breakdown_venue.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500)
for (sc, st), g in df.groupby(['scope', 'strategy'], sort=False):
    print(f'\n=== [{sc}] {st}')
    print(g[['level', 'key', 'races', 'hit', 'roi', 'roi_ex1', 'R_JulAug', 'hit_JulAug', 'roi_JulAug', 'R_Sep', 'hit_Sep', 'roi_Sep']].to_string(index=False))
