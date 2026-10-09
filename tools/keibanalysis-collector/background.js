/* 巡回収集の制御（Manifest V3 service worker）。状態は chrome.storage.local に保存し、
   service worker が休止・再起動しても続きから再開する。広告の関門は回避せず、検知したら一時停止する。 */
const BASE = 'https://keibanalysis.net/race/positionmap?raceid=';
// NAR公式の競馬場コード（raceid の9-10桁目）。帯広(ばんえい)は対象外。
// 開催確認はこの順に行う（開催の多い場を先に確認し、1場見つかればその日の開催場はリンクから判明する）
const VENUES = [['36', '門別'], ['20', '大井'], ['27', '園田'], ['24', '名古屋'], ['23', '笠松'], ['22', '金沢'], ['31', '高知'],
  ['32', '佐賀'], ['21', '川崎'], ['19', '船橋'], ['18', '浦和'], ['10', '盛岡'], ['11', '水沢'], ['28', '姫路']];
const PAGE_TIMEOUT_MS = 45000;
const NK = 'https://nar.netkeiba.com/race/result.html?race_id=';
// keibanalysis(NAR公式)の競馬場コード → netkeiba の競馬場コード（姫路51は手元データで未確認）
const NK_CODE = { '36': '30', '10': '35', '11': '36', '18': '42', '19': '43', '20': '44', '21': '45',
  '22': '46', '23': '47', '24': '48', '27': '50', '28': '51', '31': '54', '32': '55' };
const nkRaceId = (raceid) => NK_CODE[raceid.slice(8, 10)]
  ? `${raceid.slice(0, 4)}${NK_CODE[raceid.slice(8, 10)]}${raceid.slice(4, 8)}${raceid.slice(10, 12)}` : null;
const needsOdds = (r) => r && r.status === 'ok' && !r.oddsSource && r.horses.length && r.horses.every((h) => h.odds === null);
const waiters = new Map(); // raceid -> resolve

const getState = async () => (await chrome.storage.local.get('state')).state || null;
const setState = (state) => chrome.storage.local.set({ state });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function log(msg) {
  const st = await getState(); if (!st) return;
  st.log = [`${new Date().toLocaleTimeString()} ${msg}`, ...(st.log || [])].slice(0, 60);
  await setState(st);
}

// 日付はPCの現地時間で扱う（toISOString はUTCに変換されるため使わない。日本時間では前日にずれる）
const ymd = (d) => `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
function datesBetween(a, b) {
  const [ay, am, ad] = a.split('-').map(Number); const [by, bm, bd] = b.split('-').map(Number);
  const out = []; const d = new Date(ay, am - 1, ad); const end = new Date(by, bm - 1, bd);
  while (d <= end) { out.push(ymd(d)); d.setDate(d.getDate() + 1); }
  return out;
}

async function isCollected(raceid) {
  const k = `race:${raceid}`; const r = (await chrome.storage.local.get(k))[k];
  return !!(r && r.status === 'ok');
}

// 当日ページにしか無い項目は、後から取り直したページに無くても以前の値を残す（発走前の値を保持）
const KEEP = ['aiPrediction', 'riderWinLoss', 'riderOddsRange', 'stats'];
async function saveRace(data) {
  const k = `race:${data.raceid}`;
  const prev = (await chrome.storage.local.get(k))[k];
  if (prev && prev.status === 'ok') {
    for (const f of KEEP) {
      const empty = data[f] === null || data[f] === undefined || (Array.isArray(data[f]) && !data[f].length) ||
        (f === 'aiPrediction' && data[f] && !data[f].rows.length);
      if (empty && prev[f]) { data[f] = prev[f]; data[`${f}CollectedAt`] = prev[`${f}CollectedAt`] || prev.collectedAt; }
    }
    if (prev.aiPrediction && data.aiPrediction === prev.aiPrediction) {
      for (const h of data.horses) { const o = prev.horses.find((x) => x.horseNumber === h.horseNumber);
        if (o) Object.assign(h, { aiMark: o.aiMark, aiTag: o.aiTag, aiScore: o.aiScore, riderVsWin: o.riderVsWin, riderVsLoss: o.riderVsLoss }); }
    }
    data.firstCollectedAt = prev.firstCollectedAt || prev.collectedAt;
    if (!data.oddsSource && prev.oddsSource) {   // 補完済みオッズも残す
      for (const h of data.horses) { const o = prev.horses.find((x) => x.horseNumber === h.horseNumber);
        if (o && h.odds === null) { h.odds = o.odds; h.popularity = o.popularity; } }
      for (const f of ['oddsSource', 'oddsTiming', 'oddsStatus', 'oddsUrl', 'oddsCollectedAt', 'oddsMatched', 'oddsNameMismatch']) data[f] = prev[f];
    }
  }
  const idx = (await chrome.storage.local.get('raceIndex')).raceIndex || [];
  if (!idx.includes(data.raceid)) idx.push(data.raceid);
  await chrome.storage.local.set({ [k]: data, raceIndex: idx });
}

async function ensureTab(st) {
  if (st.tabId) { try { await chrome.tabs.get(st.tabId); return st.tabId; } catch (e) { /* 閉じられた */ } }
  const tab = await chrome.tabs.create({ url: 'about:blank', active: false });
  st.tabId = tab.id; await setState(st); return tab.id;
}

function waitPage(key) {
  return new Promise((resolve) => {
    const t = setTimeout(() => { waiters.delete(key); resolve(null); }, PAGE_TIMEOUT_MS);
    waiters.set(key, (d) => { clearTimeout(t); waiters.delete(key); resolve(d); });
  });
}

// netkeiba の結果ページで人気・単勝オッズ（確定）を補完する。成功/失敗の別を返す。
async function enrichOdds(st, race) {
  const nk = nkRaceId(race.raceid);
  if (!nk) { race.oddsStatus = 'no_venue_map'; return false; }
  const tabId = await ensureTab(st);
  const wait = waitPage(`nk:${nk}`);
  await chrome.tabs.update(tabId, { url: NK + nk });
  const d = await wait;
  if (!d || !d.rows.length) { race.oddsStatus = d ? 'not_found' : 'timeout'; return false; }
  const byNo = new Map(d.rows.map((r) => [r.horseNumber, r]));
  let matched = 0, nameMismatch = 0;
  for (const h of race.horses) {
    const r = byNo.get(h.horseNumber); if (!r) continue;
    h.popularity = r.popularity; h.odds = r.odds; matched++;
    if (r.horseName && h.horseName && !r.horseName.includes(h.horseName) && !h.horseName.includes(r.horseName)) nameMismatch++;
  }
  Object.assign(race, { oddsSource: 'netkeiba', oddsTiming: 'final', oddsUrl: d.url, oddsCollectedAt: new Date().toISOString(),
    oddsMatched: matched, oddsNameMismatch: nameMismatch, oddsStatus: nameMismatch ? 'name_mismatch' : 'ok' });
  return true;
}

let looping = false;
async function loop() {
  if (looping) return; looping = true;
  try {
    for (;;) {
      let st = await getState();
      if (!st || !st.running || st.paused) break;
      const item = st.queue.shift();
      if (!item) { st.running = false; st.finishedAt = new Date().toISOString(); await setState(st); await log('完了しました'); break; }
      await setState(st);
      if (st.skipCollected && await isCollected(item.raceid)) {
        const k = `race:${item.raceid}`; const saved = (await chrome.storage.local.get(k))[k];
        if (st.enrichOdds && needsOdds(saved)) {          // 取得済みでもオッズが無ければ補完だけ行う
          const ok = await enrichOdds(st, saved); await saveRace(saved);
          st = await getState(); st.counts.odds = (st.counts.odds || 0) + (ok ? 1 : 0); await setState(st);
          await log(`${item.raceid} オッズ補完 ${ok ? '成功' : '失敗(' + saved.oddsStatus + ')'}`);
          await sleep(st.delayMs + Math.floor(Math.random() * 3000));
        } else { st.counts.skipped++; await setState(st); }
        if (item.probe && saved && saved.sameDayRaceIds) {  // 開催確認の役割は果たす
          st = await getState(); const day = item.raceid.slice(0, 8); const code = item.raceid.slice(8, 10);
          const held = new Set(saved.sameDayRaceIds.map((r) => r.slice(8, 10))); held.add(code);
          const queued = new Set(st.queue.map((q) => q.raceid));
          const more = saved.sameDayRaceIds.filter((r) => r.slice(8, 10) === code && r !== item.raceid && !queued.has(r));
          st.queue = st.queue.filter((q) => !(q.probe && q.raceid.slice(0, 8) === day && !held.has(q.raceid.slice(8, 10))));
          st.queue.unshift(...more.map((r) => ({ raceid: r, probe: false })));
          await setState(st);
        }
        continue;
      }

      const tabId = await ensureTab(st);
      const wait = waitPage(`ka:${item.raceid}`);
      await chrome.tabs.update(tabId, { url: BASE + item.raceid });
      const data = await wait;
      st = await getState(); if (!st) break;

      if (!data) {
        st.counts.timeout++; await setState(st); await log(`${item.raceid} 応答なし（タイムアウト）`);
      } else if (data.status === 'blocked') {
        st.queue.unshift(item); st.paused = '広告（オファーウォール）が表示されました。収集用タブで通常どおり操作して閲覧できる状態にしてから「再開」を押してください。';
        await setState(st); await log(`${item.raceid} 広告の関門を検知 → 一時停止`);
        chrome.action.setBadgeText({ text: '!' }); break;
      } else if (data.status === 'ok') {
        if (st.enrichOdds && needsOdds(data)) {
          await setState(st);
          await sleep(st.delayMs + Math.floor(Math.random() * 3000));
          const ok = await enrichOdds(st, data);
          st = await getState(); st.counts.odds = (st.counts.odds || 0) + (ok ? 1 : 0);
          if (!ok) await log(`${item.raceid} オッズ補完 失敗(${data.oddsStatus})`);
        }
        await saveRace(data); st.counts.ok++;
        if (item.probe) {
          // 1Rで開催を確認できた場合: その場の残りレースを追加し、その日の非開催場の確認を省く
          const day = item.raceid.slice(0, 8); const code = item.raceid.slice(8, 10);
          const held = new Set(data.sameDayRaceIds.map((r) => r.slice(8, 10)));
          held.add(code);
          const queued = new Set(st.queue.map((q) => q.raceid));
          const more = data.sameDayRaceIds.filter((r) => r.slice(8, 10) === code && r !== item.raceid && !queued.has(r));
          st.queue = st.queue.filter((q) => !(q.probe && q.raceid.slice(0, 8) === day && !held.has(q.raceid.slice(8, 10))));
          st.queue.unshift(...more.map((r) => ({ raceid: r, probe: false })));
          // リンクに載っていないレースがある場合に備え、最終レースの次の番号も1つ確認する
          const last = Math.max(item.raceid.slice(10) | 0, ...more.map((r) => r.slice(10) | 0));
          st.queue.splice(more.length, 0, { raceid: `${day}${code}${String(last + 1).padStart(2, '0')}`, extend: true });
        } else if (item.extend) {
          const n = (item.raceid.slice(10) | 0) + 1;
          if (n <= 16) st.queue.unshift({ raceid: `${item.raceid.slice(0, 10)}${String(n).padStart(2, '0')}`, extend: true });
          await log(`${item.raceid} リンクに無いレースを取得 → 次の番号も確認`);
        }
        await setState(st);
        await log(`${item.raceid} ${data.venueName || ''}${data.raceNo}R ${data.runners}頭 取得`);
      } else {
        st.counts.empty++; await setState(st);
        if (!item.probe && !item.extend) await log(`${item.raceid} データなし`);
      }
      const jitter = Math.floor(Math.random() * 3000);
      await sleep(st.delayMs + jitter);
    }
  } finally { looping = false; }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg.type === 'oddsData') {
      const w = waiters.get(`nk:${msg.raceIdNk}`); const st = await getState();
      if (w && st && sender.tab && sender.tab.id === st.tabId) w(msg);
    } else if (msg.type === 'pageData') {
      const d = msg.data; const w = waiters.get(`ka:${d.raceid}`);
      const st = await getState();
      if (w && st && sender.tab && sender.tab.id === st.tabId) w(d);
      else if (d.status === 'ok') {
        const settings = (await chrome.storage.local.get('settings')).settings || {};
        if (settings.passiveCapture) { await saveRace(d); }
      }
    } else if (msg.type === 'start') {
      const { startDate, endDate, venues, delaySec, skipCollected, enrichOdds: eo } = msg;
      const order = VENUES.map(([c]) => c);
      const codes = venues && venues.length ? order.filter((c) => venues.includes(c)) : order;
      const queue = [];
      for (const day of datesBetween(startDate, endDate)) for (const c of codes) queue.push({ raceid: `${day}${c}01`, probe: true });
      const prev = await getState();
      await setState({ running: true, paused: null, queue, tabId: prev && prev.tabId, delayMs: Math.max(3, delaySec) * 1000,
        skipCollected, enrichOdds: eo !== false, counts: { ok: 0, empty: 0, skipped: 0, timeout: 0, odds: 0 }, startedAt: new Date().toISOString(), log: [] });
      chrome.action.setBadgeText({ text: '' });
      await log(`開始: ${startDate}〜${endDate} / ${codes.length}場`);
      loop();
    } else if (msg.type === 'stop') {
      const st = await getState(); if (st) { st.running = false; st.paused = null; await setState(st); await log('停止しました'); }
    } else if (msg.type === 'resume') {
      const st = await getState(); if (st) { st.running = true; st.paused = null; await setState(st); chrome.action.setBadgeText({ text: '' }); await log('再開'); loop(); }
    } else if (msg.type === 'venues') {
      sendResponse(VENUES); return;
    }
    sendResponse({ ok: true });
  })();
  return true;
});

// service worker 再起動時: 実行中なら続きから
chrome.runtime.onStartup.addListener(async () => { const st = await getState(); if (st && st.running && !st.paused) loop(); });
(async () => { const st = await getState(); if (st && st.running && !st.paused) loop(); })();
