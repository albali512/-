"""Live picker (frozen v1.0).  Usage:
  python3 predict.py --index 20260927_地方競馬指数.json --snapshots 2026-09-27/snapshots.csv [--target T-5] [--out picks.csv]
Inputs are only pre-race data: AI NAVI indices + KeibaOdds per-horse win/place odds at the target time.
Output: per race, model quinella probabilities of the top pairs and which rules (R1/R2/R3) fire."""
import argparse, json, os, itertools
import numpy as np, pandas as pd

P = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'params_v1.json')))


def norm_inv(x):
    q = 1 / x.where(x > 0)
    return q / q.sum()


def race_pairs(g):
    g = g.copy()
    g['lm'] = np.log(norm_inv(g.win_odds)); g['lmp'] = np.log(norm_inv(g.place_odds).fillna(np.exp(g.lm)).clip(1e-4))
    g['la'] = np.log(norm_inv(g.fairWinOdds)); g['lap'] = np.log(norm_inv(g.fairPlaceOdds))
    s = g[P['features']].values @ np.array(P['b']); s -= s.max()
    p = np.exp(s) / np.exp(s).sum(); pl = p ** P['lam']
    nos = g.horseNumber.values; out = []
    for i, j in itertools.combinations(range(len(p)), 2):
        pij = p[i] * pl[j] / (pl.sum() - pl[i]) + p[j] * pl[i] / (pl.sum() - pl[j])
        out.append((int(min(nos[i], nos[j])), int(max(nos[i], nos[j])), pij))
    return sorted(out, key=lambda x: -x[2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--index', required=True); ap.add_argument('--snapshots', required=True)
    ap.add_argument('--target', default='T-5'); ap.add_argument('--out')
    a = ap.parse_args()
    d = json.load(open(a.index))
    rows = []
    for m in d.get('meetings', [d]):
        for r in m['races']:
            for h in r['horses']:
                rows.append(dict(venue=m['venueName'], race_no=int(r['raceNumber']), horseNumber=h['horseNumber'],
                                 horseName=h.get('horseName'), fairWinOdds=h.get('fairWinOdds'), fairPlaceOdds=h.get('fairPlaceOdds')))
    A = pd.DataFrame(rows)
    s = pd.read_csv(a.snapshots, encoding='utf-8-sig')
    s = s[s.target == a.target][['venue', 'race_no', 'participant_no', 'win_odds', 'place_odds']]
    s = s.rename(columns={'participant_no': 'horseNumber'})
    X = A.merge(s, on=['venue', 'race_no', 'horseNumber'], how='inner')
    X = X[(X.win_odds > 0) & (X.fairWinOdds > 0) & (X.fairPlaceOdds > 0)]  # no T-x odds => scratched / not tradable
    out = []
    for (v, rn), g in X.groupby(['venue', 'race_no']):
        if len(g) < 5: continue
        pr = race_pairs(g)
        row = dict(venue=v, race_no=rn, runners=len(g))
        for name, rule in P['rules'].items():
            top = pr[:rule['k']]; cov = sum(x[2] for x in top)
            row[f'{name}_cov'] = round(cov, 3)
            row[name] = ' '.join(f'{x[0]}-{x[1]}' for x in top) if cov >= rule['c'] else ''
        row['top5_pairs'] = ' '.join(f'{x[0]}-{x[1]}({x[2]:.3f})' for x in pr[:5])
        out.append(row)
    O = pd.DataFrame(out).sort_values(['venue', 'race_no'])
    if a.out: O.to_csv(a.out, index=False, encoding='utf-8-sig')
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 20)
    print(O[['venue', 'race_no', 'runners', 'R1_top1_c30', 'R2_top2_c45', 'R2_top2_c45_cov', 'R3_top5_c60']].to_string(index=False))


if __name__ == '__main__':
    main()
