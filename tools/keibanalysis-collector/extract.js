/* positionmap ページの表示済みDOMから1レース分のデータを取り出す（ページの暗号化データは扱わない）。
   content.js と検証用スクリプトの両方から使う純粋関数。 */
(function (root) {
  const txt = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '');
  const num = (s) => { const v = parseFloat(String(s).replace(/[^\d.\-]/g, '')); return Number.isFinite(v) ? v : null; };
  const lis = (el) => (el ? Array.from(el.querySelectorAll(':scope > li')) : []);

  function parseRaceId(raceid) {
    const m = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})$/.exec(raceid || '');
    if (!m) return null;
    return { date: `${m[1]}-${m[2]}-${m[3]}`, venueCode: m[4], raceNo: parseInt(m[5], 10) };
  }

  // 「1/7」+ <span class="prize">0</span> のような成績セル
  function statCell(li) {
    if (!li) return { raw: '', stat: '', prize: null };
    const prizeEl = li.querySelector('.prize');
    const prize = prizeEl ? num(prizeEl.textContent) : null;
    const clone = li.cloneNode(true);
    clone.querySelectorAll('.prize').forEach((e) => e.remove());
    return { raw: prize === null ? txt(clone) : `${txt(clone)} ${prize}`, stat: txt(clone), prize };
  }

  function extractRace(doc, href) {
    const url = new URL(href);
    const raceid = url.searchParams.get('raceid') || '';
    const id = parseRaceId(raceid);
    const out = { raceid, url: href, collectedAt: new Date().toISOString(), status: 'ok', ...id };

    // 競馬場名: #race-info h4 → og:title/タイトル（タイトルの日付はサイト側で当日日付になるため使わない）
    const h4 = txt(doc.querySelector('#race-info h4'));
    const og = (doc.querySelector('meta[property="og:title"]') || {}).content || doc.title || '';
    let venueName = null;
    let m = /\d{4}-\d{2}-\d{2}\s+(\S+)\s+\d+R/.exec(h4);
    if (m) venueName = m[1];
    if (!venueName) { m = /(\S+?)競馬\s*\d+R/.exec(og); if (m) venueName = m[1].replace(/^.*\s/, ''); }
    out.venueName = venueName;
    out.raceName = txt(doc.querySelector('#race-info .race-name')) || null;
    out.distance = num(txt(doc.querySelector('#race-info .race-data01')));

    // ページ形式: 当日型（暗号化データをJSで描画）か過去型（サーバー描画）か
    const scripts = Array.from(doc.querySelectorAll('script:not([src])')).map((s) => s.textContent || '');
    out.pageType = scripts.some((s) => s.includes('rawData')) ? 'dynamic' : 'static';

    // レーダーチャート用データ（当日型のみ存在）: const allData = {...};
    out.stats = null;
    for (const s of scripts) {
      const mm = /const\s+allData\s*=\s*(\{[\s\S]*?\});/.exec(s);
      if (mm) { try { out.stats = JSON.parse(mm[1]); } catch (e) { /* 形式違いは無視 */ } break; }
    }

    // 出馬表
    const horses = [];
    doc.querySelectorAll('#horse-data dl').forEach((dl) => {
      const draw = dl.querySelector('dt.draw');
      if (!draw) return; // 見出し行
      const noLi = draw.querySelector('li');
      const bracket = noLi && /bracket-(\d+)/.exec(noLi.className || '');
      const jockey = lis(dl.querySelector('dd.jockey'));
      const trainer = lis(dl.querySelector('dd.trainer'));
      const sp = lis(dl.querySelector('dd.sp'));
      const present = dl.querySelector('dd.corner-position .present');
      let cornerPx = null;
      if (present) cornerPx = num((present.getAttribute('style') || '').match(/left:\s*([\d.\-]+)px/)?.[1] ?? '');
      const odds = dl.querySelectorAll('dd.odds-disp > span');
      const finishTxt = txt(dl.querySelector('dd.result-rank .rank'));
      const j1 = statCell(jockey[1]); const t1 = statCell(trainer[1]); const t2 = statCell(trainer[2]);
      horses.push({
        horseNumber: num(txt(noLi)),
        frameNumber: bracket ? parseInt(bracket[1], 10) : null, // 枠番（bracket-N）
        horseName: txt(dl.querySelector('.horse-name')),
        sex: txt(dl.querySelector('.horse_sex')),
        age: txt(dl.querySelector('.horse_age')),
        jockey: txt(jockey[0]), jockeyStat: j1.stat, jockeyPrize: j1.prize, weight: num(txt(jockey[2])),
        trainer: txt(trainer[0]), trainerStat: t1.stat, trainerPrize: t1.prize,
        // 調教師欄の3つ目: 当日型は「成績 賞金」、過去型は数値のみ等、ページ形式で中身が異なるため分けて保存
        trainerCol3: t2.stat, trainerCol3Prize: t2.prize,
        sp: num(txt(sp[0])), spRank: num(txt(sp[1])),
        cornerPx, // 予想4角位置（左からのpx。小さいほど前）
        popularity: odds[0] ? num(txt(odds[0])) : null,
        odds: odds[1] ? num(txt(odds[1])) : null,
        finish: finishTxt === '' ? null : (num(finishTxt) ?? finishTxt)
      });
    });
    // 予想4角位置の順位（px昇順）
    const withPx = horses.filter((h) => h.cornerPx !== null).sort((a, b) => a.cornerPx - b.cornerPx);
    withPx.forEach((h, i) => { h.cornerOrder = i + 1; });
    // 「有利な馬」(#superiority-horse) と「コース適性」(#superiority-course):
    //  項目名(斤量・騎手・最終角巧者・スタート巧者・馬との相性 / 馬番勝率・先行力・末脚・あがり・調子)ごとに上位の馬番を順に保存
    out.superiority = {};
    for (const sel of ['#superiority-horse', '#superiority-course']) {
      const dls = Array.from(doc.querySelectorAll(`dl${sel}`)).filter((d) => d.querySelector('dt'));
      const group = sel === '#superiority-horse' ? 'horse' : 'course';
      if (!dls.length) continue;
      dls[0].querySelectorAll(':scope > dt').forEach((dt) => {
        const dd = dt.nextElementSibling;
        if (!dd || dd.tagName !== 'DD') return;
        const nums = Array.from(dd.querySelectorAll('li')).map((li) => num(txt(li))).filter((v) => v !== null);
        out.superiority[txt(dt)] = { group, horses: nums };
      });
    }
    // 各馬に「その項目で何番目に挙がったか」(1〜) を付与
    for (const h of horses) {
      h.superiority = {};
      for (const [k, v] of Object.entries(out.superiority)) {
        const i = v.horses.indexOf(h.horseNumber);
        if (i >= 0) h.superiority[k] = i + 1;
      }
    }
    out.horses = horses;
    out.runners = horses.length;

    // 同日の他レース（同じ日付で始まる raceid のみ）
    const ids = new Set();
    doc.querySelectorAll('a[href*="positionmap?raceid="]').forEach((a) => {
      const r = /raceid=(\d{12})/.exec(a.getAttribute('href') || '');
      if (r && raceid && r[1].slice(0, 8) === raceid.slice(0, 8)) ids.add(r[1]);
    });
    out.sameDayRaceIds = Array.from(ids).sort();

    // 広告（オファーウォール）で遮られているか
    out.blocked = !horses.length && !!doc.querySelector('.fc-consent-root, .fc-dialog-container, iframe[src*="fundingchoices"], .fc-ab-root');
    if (!horses.length) out.status = out.blocked ? 'blocked' : 'empty';
    return out;
  }

  root.KTExtract = { extractRace, parseRaceId };
})(typeof window !== 'undefined' ? window : globalThis);
