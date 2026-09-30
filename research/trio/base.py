"""Weekday final & pre-final races: AI-rank positions of the top-3 finishers (baseline for trio formations)."""
import sys, json, itertools, numpy as np, pandas as pd
S = sys.argv[1] if len(sys.argv) > 1 else '.'


def load_targets(S):
    R = pd.read_parquet(f'{S}/data/races.parquet')
    H = pd.read_parquet(f'{S}/data/horses.parquet')
    R['last'] = R.groupby(['date', 'venue']).race_no.transform('max')
    R['wd'] = pd.to_datetime(R.date).dt.dayofweek
    R['slot'] = np.where(R.race_no == R['last'], 'FINAL', np.where(R.race_no == R['last'] - 1, 'MAIN', ''))
    T = R[(R.slot != '') & (R.wd <= 4) & R.has_result & (R.n_trio > 0)].copy()
    T['month'] = T.date.str[:6]
    H = H[H.rid.isin(set(T.rid))].copy()
    # PIT: 取消 is announced before purchase -> removed and ranks recomputed; 除外 (at the gate) -> refund
    H['pre_scr'] = H.fstatus.eq('取消')
    H['void'] = H.fstatus.eq('除外')
    H = H[~H.pre_scr & H.place_idx.notna()].copy()
    H['P'] = H.sort_values(['place_idx', 'horse_no'], ascending=[False, True]).groupby('rid').cumcount().reindex(H.index) + 1
    H['V'] = H.sort_values(['value_idx', 'horse_no'], ascending=[False, True]).groupby('rid').cumcount().reindex(H.index) + 1
    H['W'] = H.sort_values(['win_idx', 'horse_no'], ascending=[False, True]).groupby('rid').cumcount().reindex(H.index) + 1
    T['runners'] = T.rid.map(H.groupby('rid').size())
    return T, H


if __name__ == '__main__':
    T, H = load_targets(S)
    print('races', len(T), T.groupby(['month', 'slot']).size().unstack().to_string())
    print('runners dist', T.runners.value_counts().sort_index().to_dict())
    top3 = H[H.finish <= 3]
    for key in ['P', 'V', 'W']:
        mx = top3.groupby('rid')[key].max()
        print(key, 'box-N hit rate (worst-ranked of top3 <= N):',
              {n: round((mx <= n).mean(), 3) for n in range(3, 10)}, ' pts:', {n: len(list(itertools.combinations(range(n), 3))) for n in range(3, 8)})
    # rank of each finisher by P
    print(pd.crosstab(top3.finish, top3.P.clip(upper=9), normalize='index').round(3).to_string())
