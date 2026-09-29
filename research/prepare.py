"""Build unified race/horse tables from AI NAVI JSON + KeibaOdds time-series snapshots."""
import json, glob, os, sys
import pandas as pd, numpy as np

S = sys.argv[1] if len(sys.argv) > 1 else '.'
RAW, TS, OUT = f'{S}/raw', f'{S}/ts', f'{S}/data'
os.makedirs(OUT, exist_ok=True)

# ---------- AI NAVI ----------
hrows, rrows = [], []
for f in sorted(glob.glob(f'{RAW}/*.json')):
    d = json.load(open(f))
    meetings = d['meetings'] if 'meetings' in d else [d]
    for m in meetings:
        date = m['date']; venue = m['venueName']
        for r in m['races']:
            res = r.get('result') or {}
            pay = res.get('payouts') or {}
            q = pay.get('quinella') or []
            rid = f"{date}_{venue}_{int(r['raceNumber']):02d}"
            rrows.append(dict(rid=rid, date=date, venue=venue, race_no=int(r['raceNumber']),
                              distance=r.get('distance'), surface=r.get('surface'),
                              race_class=r.get('raceClass') or '', race_name=r.get('raceName') or '',
                              has_result=bool(res), status=res.get('status'),
                              quinella=json.dumps([[sorted(x['combination']), x['amount']] for x in q]),
                              n_quinella=len(q), src=os.path.basename(f)))
            resh = {h['horseNumber']: h for h in res.get('horses', [])}
            for h in r['horses']:
                rh = resh.get(h['horseNumber'], {})
                hrows.append(dict(rid=rid, horse_no=h['horseNumber'], name=h.get('horseName'),
                                  place_idx=h.get('placeAbilityIndex'), place_rank=h.get('placeRank'),
                                  value_idx=h.get('valueIndex'), value_rank=h.get('valueRank'),
                                  win_idx=h.get('winAbilityIndex'), win_rank=h.get('winRank'),
                                  fair_win=h.get('fairWinOdds'), fair_place=h.get('fairPlaceOdds'),
                                  finish=rh.get('finishPosition', h.get('finishPosition')),
                                  fstatus=rh.get('finishStatus', h.get('finishStatus')),
                                  scratched=rh.get('isScratched', h.get('isScratched')),
                                  final_win_odds=rh.get('finalWinOdds', h.get('finalWinOdds')),
                                  final_pop=rh.get('popularity', h.get('popularity'))))
R = pd.DataFrame(rrows); H = pd.DataFrame(hrows)
print('AI races', len(R), 'dup', R.rid.duplicated().sum(), 'horses', len(H))
R = R.drop_duplicates('rid', keep='last'); H = H.drop_duplicates(['rid', 'horse_no'], keep='last')

# ---------- KeibaOdds snapshots ----------
snaps, kraces = [], []
cols = ['race_id', 'race_date', 'venue', 'race_no', 'race_time', 'participant_no', 'target',
        'win_odds', 'win_rank', 'win_stale_over_10m', 'place_odds', 'place_rank',
        'wide_vote_rate', 'quinella_vote_rate', 'quinella_odds', 'exacta_vote_rate', 'trio_vote_rate',
        'win_observed_at', 'target_at']
for d in sorted(glob.glob(f'{TS}/20*')):
    s = pd.read_csv(f'{d}/snapshots.csv', encoding='utf-8-sig', usecols=cols, low_memory=False)
    snaps.append(s)
    kraces.append(pd.read_csv(f'{d}/races.csv', encoding='utf-8-sig'))
Sx = pd.concat(snaps); KR = pd.concat(kraces)
Sx['rid'] = Sx.race_date.str.replace('-', '') + '_' + Sx.venue + '_' + Sx.race_no.map('{:02d}'.format)
Sx = Sx.rename(columns={'participant_no': 'horse_no'})
print('snap rows', len(Sx), 'races', Sx.rid.nunique())
print('AI venues', sorted(R.venue.unique())); print('KO venues', sorted(Sx.venue.unique()))
W = Sx.pivot_table(index=['rid', 'horse_no'], columns='target',
                   values=['win_odds', 'place_odds', 'quinella_vote_rate', 'quinella_odds', 'wide_vote_rate', 'win_rank'],
                   aggfunc='first')
W.columns = [f'{a}_{b.replace("-", "")}' for a, b in W.columns]
W = W.reset_index()
stale = Sx[Sx.target.isin(['T-5', 'T-3'])].pivot_table(index=['rid', 'horse_no'], columns='target',
        values='win_stale_over_10m', aggfunc='first')
stale.columns = [f'stale_{c.replace("-", "")}' for c in stale.columns]
W = W.merge(stale.reset_index(), on=['rid', 'horse_no'], how='left')
KR['rid'] = KR.race_date.str.replace('-', '') + '_' + KR.venue + '_' + KR.race_no.map('{:02d}'.format)
KR[['rid', 'race_time', 'race_at', 'weather', 'condition', 'course', 'participant_count', 'is_finished']].to_parquet(f'{OUT}/ko_races.parquet')

HM = H.merge(W, on=['rid', 'horse_no'], how='left')
R['has_ts'] = R.rid.isin(set(W.rid))
print('AI races with ts', R.has_ts.sum(), '/', len(R))
print(R.groupby(R.date.str[:6]).agg(n=('rid', 'size'), ts=('has_ts', 'sum'), res=('has_result', 'sum')))
R.to_parquet(f'{OUT}/races.parquet'); HM.to_parquet(f'{OUT}/horses.parquet')

# ---------- fallback results from NAR CSV (races without JSON result) ----------
CSV = f'{S}/csv'
pb = pd.concat([pd.read_csv(f, encoding='utf-8-sig') for f in sorted(glob.glob(f'{CSV}/*_payback.csv'))])
pb['rid'] = pb['競走年月日'].astype(str) + '_' + pb['競馬場'] + '_' + pb['レース番号'].map('{:02d}'.format)
hl = pd.concat([pd.read_csv(f, encoding='utf-8-sig', low_memory=False,
                            usecols=['競馬場', '競走年月日', 'レース番号', '馬番', '着順'])
                for f in sorted(glob.glob(f'{CSV}/*_horselist.csv'))])
hl['rid'] = hl['競走年月日'].astype(str) + '_' + hl['競馬場'] + '_' + hl['レース番号'].map('{:02d}'.format)
hl = hl.rename(columns={'馬番': 'horse_no', '着順': 'csv_finish'})[['rid', 'horse_no', 'csv_finish']]
pb = pb[pb['馬複組番1'].notna()]  # cancelled races have no quinella combo
fb = R[~R.has_result & R.rid.isin(set(pb.rid))].rid
print('fallback races', len(fb))
pbq = pb.set_index('rid')
for rid in fb:
    x = pbq.loc[rid]
    q = [[sorted([int(x['馬複組番1']), int(x['馬複組番2'])]), int(x['馬複払戻金（円）'])]] if pd.notna(x['馬複払戻金（円）']) else []
    R.loc[R.rid == rid, ['quinella', 'n_quinella', 'has_result', 'status']] = [json.dumps(q), len(q), True, 'csv']
HM = HM.merge(hl, on=['rid', 'horse_no'], how='left')
m = HM.rid.isin(set(fb))
HM.loc[m, 'finish'] = HM.loc[m, 'csv_finish']
nofin = m & HM.finish.isna()
HM.loc[nofin, 'scratched'] = HM.loc[nofin, 'win_odds_T3'].isna()
HM.loc[nofin, 'fstatus'] = np.where(HM.loc[nofin, 'win_odds_T3'].isna(), '取消', '中止')
HM.loc[m & HM.finish.notna(), ['fstatus', 'scratched']] = ['確定', False]
HM = HM.drop(columns='csv_finish')
R.to_parquet(f'{OUT}/races.parquet'); HM.to_parquet(f'{OUT}/horses.parquet')
print('final: races with result', R.has_result.sum(), 'with quinella', (R.n_quinella > 0).sum())
