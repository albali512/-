"""荒れるレースの事前判定: 朝に分かるAI指数の形だけでレース特徴を作り、荒れ率との関係を見る。"""
import sys, json, numpy as np, pandas as pd
from reverse import load
S = sys.argv[1] if len(sys.argv) > 1 else '.'


def race_features(T, H):
    rows = []
    Tq = T.set_index('rid')
    for rid, g in H.groupby('rid'):
        g = g.sort_values('P'); pi = g.place_idx.values; wi = np.sort(g.win_idx.values)[::-1]
        fw = 1 / g.fair_win.where(g.fair_win > 0); pw = (fw / fw.sum()).fillna(0).values
        top = g[g.finish <= 2]
        win = Tq.loc[rid, 'q']; pay = max(a for c, a in win) if win else np.nan
        P1 = g.iloc[0]
        rows.append(dict(
            rid=rid, month=Tq.loc[rid, 'month'], venue=Tq.loc[rid, 'venue'], runners=len(g),
            dist=Tq.loc[rid, 'distance'], race_no=Tq.loc[rid, 'race_no'],
            p1=pi[0], p2=pi[1], p4=pi[min(3, len(pi) - 1)], w1=wi[0],
            gap12=pi[0] - pi[1], gap14=pi[0] - pi[min(3, len(pi) - 1)], wgap12=wi[0] - wi[1],
            n_close15=int((pi >= pi[0] - 15).sum()) - 1,                 # 1位から15以内の頭数
            same_top=int(P1.W == 1),                                       # 複勝1位=単勝1位
            ai_top_prob=pw.max(), ai_entropy=float(-(pw[pw > 0] * np.log(pw[pw > 0])).sum() / np.log(len(pw))),
            share_top2=(pi[:2].clip(0).sum() / max(pi.clip(0).sum(), 1)),
            # outcomes (評価専用)
            pay=pay, maxP=top.P.max() if len(top) else np.nan, minP=top.P.min() if len(top) else np.nan))
    R = pd.DataFrame(rows)
    R['upset_box4'] = (R.maxP > 4).astype(int)           # 1・2着がAI複勝上位4頭BOXで取れない
    R['upset_noP12'] = (R.minP > 2).astype(int)          # 1・2着に複勝1・2位がいない
    R['upset_pay30'] = (R.pay >= 3000).astype(int)       # 馬複30倍以上
    return R


if __name__ == '__main__':
    T, H = load(S)
    R = race_features(T, H); R.to_parquet(f'{S}/data/umaren_race_feat.parquet')
    pd.set_option('display.width', 230)
    print('base rates', R[['upset_box4', 'upset_noP12', 'upset_pay30']].mean().round(3).to_dict())
    feats = ['runners', 'p1', 'w1', 'gap12', 'gap14', 'wgap12', 'n_close15', 'ai_top_prob', 'ai_entropy', 'share_top2', 'dist']
    for f in feats:
        R['b'] = pd.qcut(R[f], 5, duplicates='drop')
        t = R.groupby(['b'], observed=True).apply(lambda x: pd.Series({
            'n': len(x), 'box4_JA': x[x.month != '202609'].upset_box4.mean(), 'box4_Sep': x[x.month == '202609'].upset_box4.mean(),
            'noP12': x.upset_noP12.mean(), 'pay30': x.upset_pay30.mean()})).round(3)
        print(f'\n[{f}]'); print(t.T.to_string())
    for f in ['same_top', 'venue']:
        t = R.groupby(f).apply(lambda x: pd.Series({'n': len(x), 'box4_JA': x[x.month != '202609'].upset_box4.mean(),
              'box4_Sep': x[x.month == '202609'].upset_box4.mean(), 'noP12': x.upset_noP12.mean(), 'pay30': x.upset_pay30.mean()})).round(3)
        print(f'\n[{f}]'); print(t.T.to_string())
