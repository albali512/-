"""軸ボーダー表・相手指数の分布・荒れ回避の効果。"""
import sys, numpy as np, pandas as pd
from reverse import load
S = sys.argv[1]
T, H = load(S)
risk = pd.read_parquet(f'{S}/data/umaren_risk_flags.parquet')
A = pd.read_parquet(f'{S}/data/umaren_axis_pre.parquet').merge(risk, on='rid')
pd.set_option('display.width', 250)
per = lambda m: np.where(m == '202609', 'Sep', 'JulAug')

# 1) axis border: P1 horse top-2 rate by (place_idx >= x) x (win_idx >= y)
p1 = H[H.P == 1].copy(); p1['per'] = per(p1.month)
print('[1] 複勝1位馬の連対率: 複勝指数≥x 行 × 単勝指数≥y 列  (7-8月 / 9月, 件数)')
for x in [50, 60, 70, 80]:
    row = []
    for y in [0, 30, 40, 50, 60]:
        d = p1[(p1.place_idx >= x) & (p1.win_idx >= y)]
        a, b = d[d.per == 'JulAug'], d[d.per == 'Sep']
        row.append(f'{a.top2.mean():.2f}/{b.top2.mean():.2f} ({len(d)})')
    print(f'  複勝≥{x}: ' + ' | '.join(f'単勝≥{y}: {r}' for y, r in zip([0, 30, 40, 50, 60], row)))

# 2) partner profile when the P1 horse was in the top 2
w = H[H.finish <= 2]
hit = p1[p1.top2 == 1].rid
part = w[w.rid.isin(hit) & (w.P != 1)].copy(); part['per'] = per(part.month)
print('\n[2] 軸(複勝1位)が連対した時の相手: 順位・指数の分布 (累積%)')
for c, edges in [('P', [2, 3, 4, 5, 6]), ('W', [2, 3, 4, 5, 6])]:
    print(f'  {c}順位≤k:', {k: f"{(part[part.per=='JulAug'][c]<=k).mean():.2f}/{(part[part.per=='Sep'][c]<=k).mean():.2f}" for k in edges})
for c, edges in [('place_idx', [60, 50, 40, 30, 20]), ('win_idx', [40, 30, 20, 10])]:
    print(f'  {c}≥t:', {t: f"{(part[part.per=='JulAug'][c]>=t).mean():.2f}/{(part[part.per=='Sep'][c]>=t).mean():.2f}" for t in edges})
# relative: partner place_idx vs axis place_idx
part = part.merge(p1[['rid', 'place_idx']].rename(columns={'place_idx': 'ax_pi'}), on='rid')
part['ratio'] = part.place_idx / part.ax_pi
print('  相手の複勝指数/軸の複勝指数 ≥r:', {r: round((part.ratio >= r).mean(), 2) for r in [0.8, 0.7, 0.6, 0.5, 0.4]})

# 3) chosen strategies with/without risk avoidance
S_ = {'軸W1 複勝≥70 単勝≥40 差≥10 → 単勝上位3頭 (3点)': (A.axis == 'W1') & (A.a_p >= 70) & (A.a_w >= 40) & (A.gap >= 10), 
      '軸W1 複勝≥70 → 複勝上位5頭 (5点)': (A.axis == 'W1') & (A.a_p >= 70),
      '軸P1 境界なし → 複勝上位3頭 (3点)': (A.axis == 'P1')}
rl = {'軸W1 複勝≥70 単勝≥40 差≥10 → 単勝上位3頭 (3点)': 'Wtop3', '軸W1 複勝≥70 → 複勝上位5頭 (5点)': 'Ptop5', '軸P1 境界なし → 複勝上位3頭 (3点)': 'Ptop3'}
print('\n[3] 荒れ回避フィルタの効果 (的中率 / 回収率 / 件数)')
for name, m in S_.items():
    p = rl[name]
    for flt_name, flt in [('全レース', True), ('荒れ注意を除外', A.risky == 0), ('堅いレースのみ', A.solid == 1)]:
        d = A[m & flt & (A[f'{p}_pts'] > 0)]
        out = []
        for pp in ['JulAug', 'Sep']:
            x = d[per(d.month) == pp]
            out.append(f'{pp} {(x[f"{p}_pay"]>0).mean():.3f} / {x[f"{p}_pay"].sum()/(x[f"{p}_pts"].sum()*100):.3f} / {len(x)}R')
        print(f'  {name} | {flt_name}: ' + ' || '.join(out))
