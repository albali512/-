"""Fit the AI-only PL3 trio model on Jul+Aug (all races) and save frozen params."""
import sys, json, pandas as pd
from model_trio import PL3, AI_FEATS
import model_eval as me  # builds HA on import
m = PL3(AI_FEATS).fit(me.HA[me.HA.month.isin(['202607', '202608']) & ~me.HA.void])
json.dump({'version': 'trio_v1.0', 'train': '2026-07-15..2026-08-31 (all races)', 'features': AI_FEATS,
           'feature_def': {'la': 'log normalized 1/fairWinOdds', 'lap': 'log normalized 1/fairPlaceOdds',
                           'pi': 'placeAbilityIndex/100', 'vi': 'valueIndex/100'},
           'b': [round(float(x), 6) for x in m.b], 'lam': round(float(m.lam), 6),
           'rule': {'target': 'weekday (Mon-Fri) final race and the race before it, per venue',
                    'K': 20, 'min_coverage': 0.55}},
          open('params_trio_v1.json', 'w'), ensure_ascii=False, indent=1)
print(open('params_trio_v1.json').read())
