const $ = (id) => document.getElementById(id);
// 現地時間で YYYY-MM-DD（toISOString はUTC変換で日付がずれるため使わない）
const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const dash = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
// 騎手のオッズ帯別3着内（「3着内数/騎乗数」で出力）
const OR_KEYS = ['〜1.9', '2.0〜9.9', '10〜19.9', '20〜29.9', '30〜99.9', '100〜'];
const SUP_KEYS = ['斤量', '騎手', '最終角巧者', 'スタート巧者', '馬との相性', '馬番勝率', '先行力', '末脚', 'あがり', '調子'];

async function init() {
  const y = new Date(); y.setDate(y.getDate() - 1);
  const saved = (await chrome.storage.local.get('settings')).settings || {};
  $('start').value = saved.start || fmt(y); $('end').value = saved.end || fmt(y);
  $('delay').value = saved.delay || 8; $('skip').checked = saved.skip !== false; $('passive').checked = !!saved.passiveCapture; $('odds').checked = saved.enrichOdds !== false;
  const venues = await chrome.runtime.sendMessage({ type: 'venues' });
  for (const [code, name] of venues) {
    const l = document.createElement('label');
    l.innerHTML = `<input type="checkbox" value="${code}" ${saved.venues && saved.venues.includes(code) ? 'checked' : ''}> ${name}`;
    $('venues').appendChild(l);
  }
  render(); setInterval(render, 1000);
}

function selectedVenues() { return Array.from(document.querySelectorAll('#venues input:checked')).map((i) => i.value); }

async function saveSettings() {
  await chrome.storage.local.set({ settings: { start: $('start').value, end: $('end').value, delay: +$('delay').value,
    skip: $('skip').checked, passiveCapture: $('passive').checked, enrichOdds: $('odds').checked, venues: selectedVenues() } });
}

async function render() {
  const { state, raceIndex } = await chrome.storage.local.get(['state', 'raceIndex']);
  const n = (raceIndex || []).length;
  const days = Array.from(new Set((raceIndex || []).map((r) => r.slice(0, 8)))).sort();
  const span = days.length ? `（${dash(days[0])}〜${dash(days[days.length - 1])}、${days.length}日分）` : '';
  if (!state) { $('status').textContent = `待機中 / 保存済み ${n}レース${span}`; return; }
  const c = state.counts || {};
  $('status').textContent = `${state.running ? (state.paused ? '一時停止中' : '収集中') : '停止'} / 残り ${state.queue.length}件（開催確認を含む）\n` +
    `取得 ${c.ok || 0} / オッズ補完 ${c.odds || 0} / データなし ${c.empty || 0} / スキップ ${c.skipped || 0} / 応答なし ${c.timeout || 0}\n保存済み合計 ${n}レース${span}`;
  $('paused').textContent = state.paused || '';
  $('log').textContent = (state.log || []).join('\n');
}

async function loadRaces() {
  const { raceIndex } = await chrome.storage.local.get('raceIndex');
  const all = (raceIndex || []).slice().sort();
  if (!all.length) { alert('保存済みのレースがありません。収集が終わっているか、ポップアップの表示を確認してください。'); return []; }
  const s = $('start').value.replace(/-/g, ''), e = $('end').value.replace(/-/g, '');
  let ids = all.filter((r) => r.slice(0, 8) >= s && r.slice(0, 8) <= e);
  if (!ids.length) {
    const d0 = dash(all[0].slice(0, 8)), d1 = dash(all[all.length - 1].slice(0, 8));
    if (!confirm(`指定期間（${$('start').value}〜${$('end').value}）のレースはありません。\n保存済みは ${d0}〜${d1} の ${all.length}レースです。全件を出力しますか？`)) return [];
    ids = all;
  }
  const got = await chrome.storage.local.get(ids.map((r) => `race:${r}`));
  return ids.map((r) => got[`race:${r}`]).filter(Boolean);
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

const csvCell = (v) => { if (v === null || v === undefined) return ''; const s = String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };

$('startBtn').onclick = async () => {
  await saveSettings();
  if ($('start').value > $('end').value) { alert('期間の指定を確認してください'); return; }
  await chrome.runtime.sendMessage({ type: 'start', startDate: $('start').value, endDate: $('end').value, venues: selectedVenues(),
    delaySec: +$('delay').value, skipCollected: $('skip').checked, enrichOdds: $('odds').checked });
};
$('todayBtn').onclick = async () => {
  // 当日ページにだけある AI予想・騎手の対戦成績・オッズ帯別3着内率 を発走前に保存する用途。
  // 取得済みも取り直し（以前の値は消えず、発走前の値は保持される）、オッズ補完は行わない。
  const t = fmt(new Date()); $('start').value = t; $('end').value = t;
  await saveSettings();
  await chrome.runtime.sendMessage({ type: 'start', startDate: t, endDate: t, venues: selectedVenues(),
    delaySec: +$('delay').value, skipCollected: false, enrichOdds: false });
};
$('stopBtn').onclick = () => chrome.runtime.sendMessage({ type: 'stop' });
$('resumeBtn').onclick = () => chrome.runtime.sendMessage({ type: 'resume' });
$('all').onclick = () => document.querySelectorAll('#venues input').forEach((i) => { i.checked = true; });
$('none').onclick = () => document.querySelectorAll('#venues input').forEach((i) => { i.checked = false; });
$('passive').onchange = saveSettings;

$('exJson').onclick = async () => {
  const races = await loadRaces();
  if (!races.length) return;
  const byDate = {};
  for (const r of races) (byDate[r.date] ||= []).push(r);
  for (const [d, rs] of Object.entries(byDate)) {
    download(`${d.replace(/-/g, '')}_keibanalysis.json`,
      JSON.stringify({ source: 'keibanalysis.net positionmap', date: d.replace(/-/g, ''), exportedAt: new Date().toISOString(), raceCount: rs.length, races: rs }, null, 1),
      'application/json');
  }
};

$('exCsv').onclick = async () => {
  const races = await loadRaces();
  if (!races.length) return;
  const head = ['raceid', 'date', 'venueCode', 'venueName', 'raceNo', 'raceName', 'distance', 'runners', 'pageType', 'collectedAt', 'oddsSource', 'oddsTiming', 'oddsStatus',
    'horseNumber', 'frameNumber', 'horseName', 'sex', 'age', 'jockey', 'jockeyStat', 'jockeyPrize', 'weight', 'trainer', 'trainerStat', 'trainerPrize', 'trainerCol3', 'trainerCol3Prize',
    'sp', 'spRank', 'cornerPx', 'cornerOrder', 'popularity', 'odds', 'finish', 'finishStatus', 'spAvailable',
    ...SUP_KEYS.map((k) => `sup_${k}`), 'aiMark', 'aiTag', 'aiScore', 'aiConfidence', 'riderVsWin', 'riderVsLoss',
    ...OR_KEYS.map((k) => `riderOdds_${k}`), 'stat_持ち時計', 'stat_陣営', 'stat_潜在力', 'stat_総合力', 'stat_近走内容'];
  const lines = [head.join(',')];
  for (const r of races) for (const h of r.horses) {
    const st = r.stats ? (r.stats[`${h.horseNumber}. ${h.horseName}`] || {}).stats || {} : {};
    const row = [r.raceid, r.date, r.venueCode, r.venueName, r.raceNo, r.raceName, r.distance, r.runners, r.pageType, r.collectedAt, r.oddsSource, r.oddsTiming, r.oddsStatus,
      h.horseNumber, h.frameNumber, h.horseName, h.sex, h.age, h.jockey, h.jockeyStat, h.jockeyPrize, h.weight, h.trainer, h.trainerStat, h.trainerPrize, h.trainerCol3, h.trainerCol3Prize,
      h.sp, h.spRank, h.cornerPx, h.cornerOrder, h.popularity, h.odds, h.finish, h.finishStatus, r.spAvailable,
      ...SUP_KEYS.map((k) => (h.superiority || {})[k]), h.aiMark, h.aiTag, h.aiScore, r.aiPrediction ? r.aiPrediction.confidence : null,
      h.riderVsWin, h.riderVsLoss, ...OR_KEYS.map((k, i) => {
        const o = (r.riderOddsRange || []).find((x) => x.horseNumber === h.horseNumber); const c = o && o.cells[i];
        return c && c.starts !== null ? `${c.top3}/${c.starts}` : null; }), st['持ち時計'], st['陣営'], st['潜在力'], st['総合力'], st['近走内容']];
    lines.push(row.map(csvCell).join(','));
  }
  download(`keibanalysis_${races[0].raceid.slice(0, 8)}_${races[races.length - 1].raceid.slice(0, 8)}.csv`, '﻿' + lines.join('\n'), 'text/csv');
};

$('clear').onclick = async () => {
  if (!confirm('取得済みデータをすべて削除します。よろしいですか？')) return;
  const all = await chrome.storage.local.get(null);
  await chrome.storage.local.remove(Object.keys(all).filter((k) => k.startsWith('race:')).concat(['raceIndex', 'state']));
};

init();
