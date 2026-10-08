/* nar.netkeiba.com の結果ページから、馬番ごとの人気・単勝オッズ（確定）を読み取って background に送る。
   列は見出し文字（馬番・人気・オッズ/単勝）で探すので、列の並びが多少変わっても読める。 */
(async function () {
  const raceIdNk = new URL(location.href).searchParams.get('race_id');
  if (!raceIdNk) return;
  const txt = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '');
  const num = (s) => { const v = parseFloat(String(s).replace(/[^\d.]/g, '')); return Number.isFinite(v) ? v : null; };

  function parse() {
    for (const table of document.querySelectorAll('table')) {
      const headRow = Array.from(table.querySelectorAll('tr')).find((tr) => tr.querySelector('th'));
      if (!headRow) continue;
      const heads = Array.from(headRow.children).map(txt);
      const iNo = heads.findIndex((h) => h === '馬番' || h.startsWith('馬番'));
      const iPop = heads.findIndex((h) => h.includes('人気'));
      const iOdds = heads.findIndex((h) => h.includes('オッズ') || h === '単勝');
      if (iNo < 0 || iPop < 0 || iOdds < 0) continue;
      const iName = heads.findIndex((h) => h.includes('馬名'));
      const iRank = heads.findIndex((h) => h.includes('着順') || h === '着');
      const rows = [];
      for (const tr of table.querySelectorAll('tr')) {
        if (tr === headRow) continue;
        const td = Array.from(tr.children);
        if (td.length < heads.length - 1) continue;
        const no = num(txt(td[iNo]));
        if (no === null) continue;
        rows.push({ horseNumber: no, horseName: iName >= 0 ? txt(td[iName]) : null,
          rankText: iRank >= 0 ? txt(td[iRank]) : null, popularity: num(txt(td[iPop])), odds: num(txt(td[iOdds])) });
      }
      if (rows.length) return rows;
    }
    return [];
  }

  let rows = [];
  for (let i = 0; i < 20 && !rows.length; i++) { rows = parse(); if (!rows.length) await new Promise((r) => setTimeout(r, 500)); }
  try { chrome.runtime.sendMessage({ type: 'oddsData', raceIdNk, url: location.href, rows }); } catch (e) { /* 拡張の再読込中など */ }
})();
