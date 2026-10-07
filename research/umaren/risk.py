"""荒れリスク: (1) ロジスティック回帰スコア, (2) 人が使える単純ルール。7-8月で作り9月で検証。"""
import sys, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.tree import DecisionTreeClassifier, export_text
S = sys.argv[1]
R = pd.read_parquet(f'{S}/data/umaren_race_feat.parquet')
F = ['runners', 'p1', 'w1', 'gap12', 'gap14', 'n_close15', 'ai_top_prob', 'share_top2', 'same_top']
E, V = R[R.month != '202609'], R[R.month == '202609']
out = {}
for y in ['upset_box4', 'upset_noP12']:
    lr = LogisticRegression(max_iter=2000).fit((E[F] - E[F].mean()) / E[F].std(), E[y])
    pv = lr.predict_proba((V[F] - E[F].mean()) / E[F].std())[:, 1]
    print(y, 'logit AUC explore %.3f / Sep %.3f' % (roc_auc_score(E[y], lr.predict_proba((E[F] - E[F].mean()) / E[F].std())[:, 1]), roc_auc_score(V[y], pv)),
          dict(zip(F, lr.coef_[0].round(2))))
    for f in F:
        a = roc_auc_score(V[y], V[f]); print('   single', f, 'Sep AUC %.3f' % max(a, 1 - a))
    tr = DecisionTreeClassifier(max_depth=2, min_samples_leaf=150).fit(E[F], E[y])
    print(export_text(tr, feature_names=F, decimals=1))
    leaf_e = pd.Series(tr.apply(E[F])); leaf_v = pd.Series(tr.apply(V[F]))
    print(pd.DataFrame({'n_JA': leaf_e.value_counts(), 'rate_JA': E[y].groupby(leaf_e.values).mean().round(3),
                        'n_Sep': leaf_v.value_counts(), 'rate_Sep': V[y].groupby(leaf_v.values).mean().round(3)}).to_string())
# Simple hand rule (defined from the univariate table on Jul-Aug): risky if runners>=12 or n_close15>=3 or w1<30
R['risky'] = ((R.runners >= 12) | (R.n_close15 >= 3) | (R.w1 < 30)).astype(int)
R['solid'] = ((R.runners <= 10) & (R.n_close15 <= 1) & (R.w1 >= 40)).astype(int)
for c in ['risky', 'solid']:
    print(c, R.groupby(['month', c]).agg(n=('rid', 'size'), box4=('upset_box4', 'mean'), noP12=('upset_noP12', 'mean'), pay30=('upset_pay30', 'mean')).round(3).to_string())
R[['rid', 'risky', 'solid']].to_parquet(f'{S}/data/umaren_risk_flags.parquet')
