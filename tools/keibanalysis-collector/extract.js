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
    if (!venueName) { m = /^(\S+)\s+\d+R/.exec(txt(doc.querySelector('.race-navi .course-dsp'))); if (m) venueName = m[1]; }
    const JRA = ['札幌', '函館', '福島', '新潟', '東京', '中山', '中京', '京都', '阪神', '小倉'];
    out.circuit = venueName && JRA.includes(venueName) ? 'JRA' : 'NAR';
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

    // 予想4角位置がCSSルール(.position-pad-N{left:Xpx})で指定されている場合（中央の結果ページなど）
    const padLeft = {};
    doc.querySelectorAll('style').forEach((st) => {
      const re = /\.position-pad-(\d+)\s*\{[^}]*?left:\s*([\d.\-]+)px/g; let mm;
      while ((mm = re.exec(st.textContent || ''))) padLeft[mm[1]] = parseFloat(mm[2]);
    });
    // レーダーチャートの値: スクリプト内 allData が無い場合は、グラフ要素の data-stats 属性から読む
    if (!out.stats) {
      const st = {};
      doc.querySelectorAll('.chart-box').forEach((box) => {
        const svg = box.querySelector('[data-stats]'); if (!svg) return;
        try { st[txt(box.querySelector('.chart-title'))] = { stats: JSON.parse(svg.getAttribute('data-stats')),
          missing: JSON.parse(svg.getAttribute('data-missing') || '[]') }; } catch (e) { /* 形式違いは無視 */ }
      });
      if (Object.keys(st).length) out.stats = st;
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
      if (present && cornerPx === null) { const pc = /position-pad-(\d+)/.exec(present.className || ''); if (pc && padLeft[pc[1]] !== undefined) cornerPx = padLeft[pc[1]]; }
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
        // 着順は数値のみ。取消・除外・中止などの文字は finishStatus に分ける
        finish: /^\d+$/.test(finishTxt) ? parseInt(finishTxt, 10) : null,
        finishStatus: finishTxt === '' ? null : (/^\d+$/.test(finishTxt) ? '確定' : finishTxt)
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
    // --- 当日ページのみにある3項目 ---
    // (1) AI予想: 印(◎○▲△)・馬番・馬名・スコア%、展開有利(🚀)・データ特注穴馬(⚡)
    out.aiPrediction = null;
    const card = doc.querySelector('.ai-prediction-card');
    if (card) {
      const rows = [];
      card.querySelectorAll('table.prediction-table tr').forEach((tr, i) => {
        const markTd = tr.querySelector('td.col-mark');
        const no = num(txt(tr.querySelector('.gate-number')));
        if (no === null) return;
        let mark = null, tag = null, markShape = null;
        const pace = markTd && markTd.querySelector('span[title]');
        if (pace) { tag = pace.getAttribute('title'); mark = txt(pace); }
        else if (markTd) {
          // 既知の図形と完全一致した時だけ印を付ける。それ以外は図形情報を残して mark='不明'
          const circles = Array.from(markTd.querySelectorAll('circle'));
          const paths = Array.from(markTd.querySelectorAll('path'));
          markShape = [...circles.map((c) => `circle r=${c.getAttribute('r')} fill=${c.getAttribute('fill')} stroke=${c.getAttribute('stroke')}`),
            ...paths.map((p) => `path d=${p.getAttribute('d')} fill=${p.getAttribute('fill')} stroke=${p.getAttribute('stroke')}`)].join(' | ') || txt(markTd) || null;
          const p0 = paths[0], fill = p0 ? (p0.getAttribute('fill') || 'none') : null, d = p0 ? p0.getAttribute('d') : null;
          if (circles.length === 2 && !paths.length) mark = '◎';
          else if (circles.length === 1 && !paths.length && (circles[0].getAttribute('fill') || 'none') === 'none') mark = '○';
          else if (!circles.length && paths.length === 1 && d === 'M12 3L22 20H2L12 3Z' && fill !== 'none') mark = '▲';
          else if (!circles.length && paths.length === 1 && d === 'M12 4L21 19H3Z' && fill === 'none') mark = '△';
          else if (!circles.length && paths.length === 1 && d && d.startsWith('M12 1.5l2.8 6.2') && fill !== 'none') mark = '★'; // 星（10/9 大井3R等で確認）
          else mark = markShape ? '不明' : null;
        }
        const bar = tr.querySelector('.score-bar-fill');
        const score = bar ? num(((bar.getAttribute('style') || '').match(/width:\s*([\d.]+)%/) || [])[1] ?? '') : null;
        rows.push({ order: i + 1, mark, tag, markShape: mark === '不明' ? markShape : null, horseNumber: no, horseName: txt(tr.querySelector('td[class*="col-horse"]')) || null,
          trend: txt(tr.querySelector('td.col-trend')) || null, score });
      });
      out.aiPrediction = { version: txt(card.querySelector('h2')) || null,
        confidence: card.querySelectorAll('.tier-gauge .gauge-block.active').length,
        confidenceMax: card.querySelectorAll('.tier-gauge .gauge-block').length, rows };
    }
    // 騎手の2つの表は、タブ切替用のHTML文字列としてスクリプト内にある（画面には未表示）。
    // まず画面上の表を探し、無ければスクリプト内の文字列から取り出して解析する。
    const findTable = (id) => {
      const live = doc.querySelector(`table#${id}`);
      if (live) return live;
      for (const s of scripts) {
        const i = s.indexOf(`<table id="${id}"`); if (i < 0) continue;
        const j = s.indexOf('</table>', i); if (j < 0) continue;
        const html = s.slice(i, j + 8).replace(/\\'/g, "'").replace(/\\"/g, '"').replace(/\\\//g, '/');
        const parsed = new DOMParser().parseFromString(`<html><body>${html}</body></html>`, 'text/html');
        const t = parsed.querySelector(`table#${id}`); if (t) return t;
      }
      return null;
    };
    const riderRowNo = (td) => num(txt(td.querySelector('.waku'))); // 行見出しの番号（馬番）
    // (2) 騎手の対戦成績表 (#winLossTable): 行の騎手から見た 列の騎手との 先着-後着
    out.riderWinLoss = null;
    const wl = findTable('winLossTable');
    if (wl) {
      const heads = Array.from(wl.querySelectorAll('th')).slice(1).map(txt);
      const rows = [];
      wl.querySelectorAll('tbody tr').forEach((tr) => {
        const tds = Array.from(tr.children); if (!tds.length) return;
        const vs = [];
        tds.slice(1).forEach((td, k) => {
          const m2 = /(\d+)\s*-\s*(\d+)/.exec(txt(td));
          if (m2) vs.push({ opponent: heads[k], win: +m2[1], loss: +m2[2], cls: td.className || null });
        });
        rows.push({ horseNumber: riderRowNo(tds[0]), rider: txt(tds[0].querySelector('div:not(.waku)')) || null, vs });
      });
      out.riderWinLoss = rows;
    }
    // (3) 騎手のオッズ帯別3着内率 (#oddsRangeTable)
    out.riderOddsRange = null;
    const orT = findTable('oddsRangeTable');
    if (orT) {
      const ranges = Array.from(orT.querySelectorAll('thead th')).slice(1).map(txt);
      const rows = [];
      orT.querySelectorAll('tbody tr').forEach((tr) => {
        const tds = Array.from(tr.children); if (!tds.length) return;
        const cells = tds.slice(1).map((td, k) => {
          const m3 = /\(\s*(\d+)\s*\/\s*(\d+)\s*\)/.exec(txt(td)); const pct = /([\d.]+)%/.exec(txt(td));
          return { range: ranges[k], top3: m3 ? +m3[1] : null, starts: m3 ? +m3[2] : null, rate: pct ? +pct[1] : null };
        });
        rows.push({ horseNumber: riderRowNo(tds[0]), rider: txt(tds[0].querySelector('.t-d-name')) || null,
          oddsDisp: txt(tds[0].querySelector('.odds-disp')) || null, cells });
      });
      out.riderOddsRange = rows;
    }
    // 各馬に要約を付与（CSV用）
    for (const h of horses) {
      const a = out.aiPrediction && out.aiPrediction.rows.find((r) => r.horseNumber === h.horseNumber);
      h.aiMark = a ? a.mark : null; h.aiTag = a ? a.tag : null; h.aiScore = a ? a.score : null;
      const w = out.riderWinLoss && out.riderWinLoss.find((r) => r.horseNumber === h.horseNumber);
      h.riderVsWin = w ? w.vs.reduce((s, x) => s + x.win, 0) : null;
      h.riderVsLoss = w ? w.vs.reduce((s, x) => s + x.loss, 0) : null;
    }

    out.horses = horses;
    out.runners = horses.length;
    // 発走前（着順がまだ1頭も無い）ページのオッズは前売りオッズとして別欄へ。odds は確定オッズ専用にする
    if (horses.length && horses.every((h) => h.finish === null && !h.finishStatus) && horses.some((h) => h.odds !== null)) {
      for (const h of horses) { h.preOdds = h.odds; h.prePopularity = h.popularity; h.odds = null; h.popularity = null; }
      out.preOddsCollectedAt = out.collectedAt;
    }
    // 新馬戦などでSPが全頭空欄のレース
    out.spAvailable = horses.some((h) => h.sp !== null);

    // 同日の他レース（同じ日付で始まる raceid のみ）
    const ids = new Set();
    doc.querySelectorAll('a[href*="positionmap?raceid="], a[href*="result_race?raceid="]').forEach((a) => {
      const r = /raceid=(\d{12})/.exec(a.getAttribute('href') || '');
      if (r && raceid && r[1].slice(0, 8) === raceid.slice(0, 8)) ids.add(r[1]);
    });
    out.sameDayRaceIds = Array.from(ids).sort();

    // 払戻金（#payoff-layout。結果確定後のページ）: 券種ごとに 組番・払戻(円)・人気
    out.payouts = null;
    const pay = doc.querySelector('#payoff-layout');
    if (pay) {
      out.payouts = {};
      pay.querySelectorAll('li > dl').forEach((dl) => {
        const kind = txt(dl.querySelector('dt')); if (!kind) return;
        out.payouts[kind] = Array.from(dl.querySelectorAll('dd .line')).map((ln) => ({
          combination: txt(ln.querySelector('.num')), yen: num(txt(ln.querySelector('.payoff'))), popularity: num(txt(ln.querySelector('.pop'))) }));
      });
      if (!Object.keys(out.payouts).length) out.payouts = null;
    }
    // 広告（オファーウォール）で遮られているか
    out.blocked = !horses.length && !!doc.querySelector('.fc-consent-root, .fc-dialog-container, iframe[src*="fundingchoices"], .fc-ab-root');
    if (!horses.length) out.status = out.blocked ? 'blocked' : 'empty';
    return out;
  }

  root.KTExtract = { extractRace, parseRaceId };
})(typeof window !== 'undefined' ? window : globalThis);
