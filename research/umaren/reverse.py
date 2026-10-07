"""馬複の結果から逆算: 1・2着馬のAI複勝指数/単勝指数・順位の分布、軸候補の連対率。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, '../trio')
from base import load_targets
S = sys.argv[1]


def load(S):
    T, H = load_targets(S, 'all')
    T = T.copy()
    T['q'] = T.quinella.map(json.loads)
    H = H.merge(T[['rid', 'month', 'venue', 'runners']], on='rid')
    H['top2'] = (H.finish <= 2).astype(int)
    # race-level index context (morning-available only)
    g = H.groupby('rid')
    for k in ['place_idx', 'win_idx']:
        H[f'{k}_r1'] = g[k].transform(lambda s: s.nlargest(1).iloc[-1])
        H[f'{k}_r2'] = g[k].transform(lambda s: s.nlargest(2).iloc[-1] if len(s) > 1 else np.nan)
    return T, H


if __name__ == '__main__':
    T, H = load(S)
    pd.set_option('display.width', 220)
    w = H[H.finish <= 2]
    print('races', T.rid.nunique(), 'horses', len(H))
    print('\n連対馬の複勝順位P分布(%)'); print((w.P.clip(upper=9).value_counts(normalize=True).sort_index() * 100).round(1).to_dict())
    print('連対馬の単勝順位W分布(%)'); print((w.W.clip(upper=9).value_counts(normalize=True).sort_index() * 100).round(1).to_dict())
    # pair-level: ranks of the two
    pr = w.groupby('rid').P.apply(lambda s: tuple(sorted(s.clip(upper=9))))
    print('\n馬複的中組の複勝順位ペア 上位15 (%):'); print((pr.value_counts(normalize=True).head(15) * 100).round(1).to_dict())
    print('P1を含む', round(w.groupby('rid').P.min().eq(1).mean() * 100, 1), '% / P1-P2を含む', round(w.groupby('rid').P.min().le(2).mean() * 100, 1),
          '% / 両方P上位4以内', round(w.groupby('rid').P.max().le(4).mean() * 100, 1), '%')
    # axis candidate: P1 horse -> top2 rate by its place_idx band and win_idx band
    p1 = H[H.P == 1].copy()
    p1['pb'] = pd.cut(p1.place_idx, [-100, 30, 40, 50, 60, 70, 80, 200])
    p1['wb'] = pd.cut(p1.win_idx, [-100, 10, 20, 30, 40, 50, 200])
    print('\nP1馬の連対率 × 複勝指数帯 (n, 連対率)')
    print(p1.groupby('pb', observed=True).top2.agg(['size', 'mean']).round(3).T.to_string())
    print('P1馬の連対率 × 単勝指数帯')
    print(p1.groupby('wb', observed=True).top2.agg(['size', 'mean']).round(3).T.to_string())
    print('P1馬 連対率 クロス(複勝指数帯×単勝指数帯)')
    print(p1.pivot_table(index='pb', columns='wb', values='top2', aggfunc='mean', observed=True).round(2).to_string())
    print(p1.pivot_table(index='pb', columns='wb', values='top2', aggfunc='size', observed=True).to_string())
    # gap P1-P2 place idx
    H2 = H[H.P == 2][['rid', 'place_idx']].rename(columns={'place_idx': 'p2'})
    p1 = p1.merge(H2, on='rid'); p1['gap'] = p1.place_idx - p1.p2
    p1['gb'] = pd.cut(p1.gap, [-1, 3, 6, 10, 15, 20, 30, 200])
    print('P1連対率 × (P1-P2複勝指数差)'); print(p1.groupby('gb', observed=True).top2.agg(['size', 'mean']).round(3).T.to_string())
