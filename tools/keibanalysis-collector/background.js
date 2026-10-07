/* 巡回収集の制御（Manifest V3 service worker）。状態は chrome.storage.local に保存し、
   service worker が休止・再起動しても続きから再開する。広告の関門は回避せず、検知したら一時停止する。 */
const BASE = 'https://keibanalysis.net/race/positionmap?raceid=';
// NAR公式の競馬場コード（raceid の9-10桁目）。帯広(ばんえい)は対象外。
// 開催確認はこの順に行う（開催の多い場を先に確認し、1場見つかればその日の開催場はリンクから判明する）
const VENUES = [['36', '門別'], ['20', '大井'], ['27', '園田'], ['24', '名古屋'], ['23', '笠松'], ['22', '金沢'], ['31', '高知'],
  ['32', '佐賀'], ['21', '川崎'], ['19', '船橋'], ['18', '浦和'], ['10', '盛岡'], ['11', '水沢'], ['28', '姫路']];
const PAGE_TIMEOUT_MS = 45000;
const waiters = new Map(); // raceid -> resolve

const getState = async () => (await chrome.storage.local.get('state')).state || null;
const setState = (state) => chrome.storage.local.set({ state });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function log(msg) {
  const st = await getState(); if (!st) return;
  st.log = [`${new Date().toLocaleTimeString()} ${msg}`, ...(st.log || [])].slice(0, 60);
  await setState(st);
}

function datesBetween(a, b) {
  const out = []; const d = new Date(a + 'T00:00:00'); const end = new Date(b + 'T00:00:00');
  while (d <= end) { out.push(d.toISOString().slice(0, 10).replace(/-/g, '')); d.setDate(d.getDate() + 1); }
  return out;
}

async function isCollected(raceid) {
  const k = `race:${raceid}`; const r = (await chrome.storage.local.get(k))[k];
  return !!(r && r.status === 'ok');
}

async function saveRace(data) {
  const k = `race:${data.raceid}`;
  const idx = (await chrome.storage.local.get('raceIndex')).raceIndex || [];
  if (!idx.includes(data.raceid)) idx.push(data.raceid);
  await chrome.storage.local.set({ [k]: data, raceIndex: idx });
}

async function ensureTab(st) {
  if (st.tabId) { try { await chrome.tabs.get(st.tabId); return st.tabId; } catch (e) { /* 閉じられた */ } }
  const tab = await chrome.tabs.create({ url: 'about:blank', active: false });
  st.tabId = tab.id; await setState(st); return tab.id;
}

function waitPage(raceid) {
  return new Promise((resolve) => {
    const t = setTimeout(() => { waiters.delete(raceid); resolve(null); }, PAGE_TIMEOUT_MS);
    waiters.set(raceid, (d) => { clearTimeout(t); waiters.delete(raceid); resolve(d); });
  });
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
      if (st.skipCollected && await isCollected(item.raceid)) { st.counts.skipped++; await setState(st); continue; }

      const tabId = await ensureTab(st);
      const wait = waitPage(item.raceid);
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
        }
        await setState(st);
        await log(`${item.raceid} ${data.venueName || ''}${data.raceNo}R ${data.runners}頭 取得`);
      } else {
        st.counts.empty++; await setState(st);
        if (!item.probe) await log(`${item.raceid} データなし`);
      }
      const jitter = Math.floor(Math.random() * 3000);
      await sleep(st.delayMs + jitter);
    }
  } finally { looping = false; }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg.type === 'pageData') {
      const d = msg.data; const w = waiters.get(d.raceid);
      const st = await getState();
      if (w && st && sender.tab && sender.tab.id === st.tabId) w(d);
      else if (d.status === 'ok') {
        const settings = (await chrome.storage.local.get('settings')).settings || {};
        if (settings.passiveCapture) { await saveRace(d); }
      }
    } else if (msg.type === 'start') {
      const { startDate, endDate, venues, delaySec, skipCollected } = msg;
      const order = VENUES.map(([c]) => c);
      const codes = venues && venues.length ? order.filter((c) => venues.includes(c)) : order;
      const queue = [];
      for (const day of datesBetween(startDate, endDate)) for (const c of codes) queue.push({ raceid: `${day}${c}01`, probe: true });
      const prev = await getState();
      await setState({ running: true, paused: null, queue, tabId: prev && prev.tabId, delayMs: Math.max(3, delaySec) * 1000,
        skipCollected, counts: { ok: 0, empty: 0, skipped: 0, timeout: 0 }, startedAt: new Date().toISOString(), log: [] });
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
