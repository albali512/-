/* 表示が完了するまで待ってから抽出し、background に送る。 */
(async function () {
  const raceid = new URL(location.href).searchParams.get('raceid');
  if (!raceid) return;
  // 出馬表の行が出るまで待つ。枠(#horse-data)があるのに行が出ない場合は開催なしとみなして早めに打ち切る
  const start = Date.now();
  const ready = () => document.querySelectorAll('#horse-data dl dt.draw').length > 0;
  const giveUp = () => Date.now() - start > (document.getElementById('horse-data') ? 8000 : 20000);
  while (!ready() && !giveUp()) {
    await new Promise((r) => setTimeout(r, 500));
  }
  if (ready()) await new Promise((r) => setTimeout(r, 1000)); // 4角位置の描画を待つ
  const data = window.KTExtract.extractRace(document, location.href);
  try { chrome.runtime.sendMessage({ type: 'pageData', data }); } catch (e) { /* 拡張の再読込中など */ }
})();
