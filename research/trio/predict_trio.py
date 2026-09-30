"""Live trio picker (frozen trio_v1.0, AI NAVI only - usable in the morning).
  python3 predict_trio.py --index 20261001_地方競馬指数.json [--K 20] [--min-cov 0.55] [--scratch 大井:11:5,...] [--out picks.csv]
Targets: on Mon-Fri, each venue's final race and the race before it.  Scratched (取消) horses are removed
(isScratched in the JSON or --scratch); a horse excluded later (除外) makes its tickets refunds."""
import argparse, json, os, itertools, datetime
import numpy as np, pandas as pd

P = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'params_trio_v1.json')))


def triples(g):
    q = lambda c: (1 / g[c]) / (1 / g[c]).sum()
    X = np.c_[np.log(q('fairWinOdds')), np.log(q('fairPlaceOdds')), g.placeAbilityIndex / 100, g.valueIndex / 100]
    s = X @ np.array(P['b']); s -= s.max(); p = np.exp(s) / np.exp(s).sum(); w = p ** P['lam']
    nos = g.horseNumber.values; out = {}
    for i, j, l in itertools.permutations(range(len(p)), 3):
        key = tuple(sorted((int(nos[i]), int(nos[j]), int(nos[l]))))
        out[key] = out.get(key, 0) + p[i] * w[j] / (w.sum() - w[i]) * w[l] / (w.sum() - w[i] - w[j])
    return sorted(out.items(), key=lambda x: -x[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--index', required=True); ap.add_argument('--K', type=int, default=P['rule']['K'])
    ap.add_argument('--min-cov', type=float, default=P['rule']['min_coverage']); ap.add_argument('--scratch', default='')
    ap.add_argument('--all-days', action='store_true', help='also run on Sat/Sun'); ap.add_argument('--out')
    a = ap.parse_args()
    scr = {tuple(x.split(':')) for x in a.scratch.split(',') if x}
    d = json.load(open(a.index)); rows = []
    for m in d.get('meetings', [d]):
        date = datetime.date(int(m['date'][:4]), int(m['date'][4:6]), int(m['date'][6:]))
        if date.weekday() > 4 and not a.all_days: continue
        last = max(int(r['raceNumber']) for r in m['races'])
        for r in m['races']:
            rn = int(r['raceNumber'])
            if rn < last - 1: continue
            g = pd.DataFrame(r['horses'])
            g = g[~g.get('isScratched', pd.Series(False, index=g.index)).fillna(False).astype(bool)]
            g = g[~g.horseNumber.map(lambda n: (m['venueName'], str(rn), str(n)) in scr)]
            g = g.dropna(subset=['fairWinOdds', 'fairPlaceOdds', 'placeAbilityIndex', 'valueIndex'])
            if len(g) < 4: continue
            tri = triples(g); top = tri[:a.K]; cov = sum(p for _, p in top)
            rows.append(dict(venue=m['venueName'], race_no=rn, slot='FINAL' if rn == last else 'MAIN', runners=len(g),
                             pred_hit=round(cov, 3), BUY='○' if cov >= a.min_cov else '',
                             tickets=' '.join('-'.join(map(str, t)) for t, _ in top)))
    O = pd.DataFrame(rows)
    if a.out: O.to_csv(a.out, index=False, encoding='utf-8-sig')
    pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 200)
    print(O.to_string(index=False) if len(O) else 'no weekday target races')


if __name__ == '__main__':
    main()
