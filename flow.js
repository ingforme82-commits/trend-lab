"use strict";
(() => {
  const section = document.createElement('section');
  section.className = 'sec sec-alt';
  section.id = 'flowDesk';
  section.innerHTML = `<div class="wrap"><div class="sec-head"><div><h2>지수 흐름 · 분할과 비중의 근거</h2><p class="sec-sub">지수 추세 → 현재 비중 → 분할 계획 → 실행 기록을 순서대로 확인합니다.</p></div></div><div id="flowStatus" class="fine" role="status"></div><div id="flowIndices" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:18px 0"></div><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px"><div><h3>최근 움직임과 시각이 겹친 뉴스</h3><div id="flowMoves"></div><p class="fine">같은 시각의 움직임은 인과관계 증명이 아닙니다. 정규 지수·선물·24시간 프록시는 서로 구분합니다.</p></div><div><h3>추세를 확인하는 순서</h3><ol><li>당일 등락과 일봉 추세를 나눠 확인</li><li>종가의 5·10일선 위치·기울기와 회복 유지 여부 확인</li><li>시장 내 상승 종목 확산·거래대금·수급 대조</li><li>본인 계좌의 현재 비중·현금·기존 분할 규칙 대조</li><li>판단·주문 시도·체결·비용 차감 결과를 따로 기록</li></ol><p class="fine">아래 숫자는 당일 변화입니다. 일봉 이동평균 확인 없이 추세 전환이나 주문 신호로 표시하지 않습니다. 개인 비중과 매매 기록은 비공개 운영실에서 확인합니다.</p><h3>뉴스 수신 확인</h3><div id="flowNews"></div></div></div></div>`;
  const anchor = document.querySelector('#top .hero');
  if (anchor) anchor.after(section); else document.querySelector('main').prepend(section);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clock = value => Number.isFinite(value) ? new Date(value).toLocaleTimeString('ko-KR', {hour12:false,timeZone:'Asia/Seoul'}) : '시각 미기록';
  const age = value => !Number.isFinite(value) || value <= 0 ? '미확인' : value > Date.now()+1000 ? '시계 확인 필요' : `${Math.floor((Date.now()-value)/1000)}초 전`;
  function render() {
    const rt = window.trlRt || {}, health = window.trlRtHealth;
    const fresh = Object.values(rt.q || {}).filter(row => TRLFlow.quoteState(row) === 'recent').length;
    const net = health?.ok ? `${Math.round(health.roundTripMs)}ms 왕복` : '재확인 전·연결 실패';
    document.getElementById('flowStatus').textContent = `시세 경로 ${net} · 최근 수신 종목 ${fresh}개 · 뉴스 게시 ${age(window.trlUpdated)} · 서버 수신 시각과 거래소 체결 시각은 다릅니다.`;
    const snapshot = [['KOSPI','코스피',window.trlKr?.KOSPI],['KR200','코스피200',window.trlKr?.KR200],['KOSDAQ','코스닥',window.trlKr?.KOSDAQ],['SP500','S&P500',window.trlReg?.SP500],['XYZ100','나스닥100',window.trlReg?.XYZ100]];
    document.getElementById('flowIndices').innerHTML = snapshot.map(([key,name,row]) => {
      const tick = rt.q?.[key], recent = TRLFlow.quoteState(tick) === 'recent';
      const px = recent ? tick.px : row?.px;
      const chg = recent && Number.isFinite(tick.ref) && tick.ref > 0 ? (tick.px/tick.ref-1)*100 : TRLFlow.dailyDirection(row);
      const label = recent ? 'KIS 서버 최근 수신' : row?.open === false ? '장 종료 · 마지막 시세' : '수집 시세 · 원천 확인';
      return `<article class="tick"><p class="t-name">${name}</p><p class="t-px">${Number.isFinite(px) ? px.toLocaleString('ko-KR',{maximumFractionDigits:2}) : '미확인'}</p><p class="t-ch ${chg > 0 ? 'c-up' : chg < 0 ? 'c-dn' : 'c-fl'}">${Number.isFinite(chg) ? (chg > 0 ? '+' : '') + chg.toFixed(2) + '%' : '비교 기준 미확인'}</p><p class="fine">기준 전일 종가 · ${clock(recent ? tick.at : row?.at)}<br>${label}<br>일봉 추세 확인은 별도</p></article>`;
    }).join('');
    document.getElementById('flowMoves').innerHTML = [...(window.trlMoves || [])].sort((a,b) => b.start-a.start).slice(0,4).map(row => `<p><b>${esc(row.name || row.asset)}</b> ${Number.isFinite(row.move) ? esc(row.move) : '미확인'}${row.unit === 'bp' ? 'bp' : '%'} · ${clock(row.start)}<br><small>${esc(row.session || '')}${['K200','NQ','SP','WTI','BRENT','GOLD'].includes(row.asset) ? ' · 24시간 프록시 관측' : ''}</small><br>${(row.items || []).slice(0,2).map(item => '<small>' + esc(item.src) + ' · ' + clock(item.ts) + ' · ' + esc(item.text) + '</small>').join('<br>')}</p>`).join('') || '<p class="fine">확인할 급변 기록이 없습니다. 추세가 없다는 뜻은 아닙니다.</p>';
    const route = window.trlNewsHealth?.direct ? '오라클 직접 수신 · 게시본 10초 재확인' : 'GitHub 게시본 · 기본 경로';
    document.getElementById('flowNews').innerHTML = `<p class="fine">${esc(route)} · 수집 주기 자체가 10초로 바뀌는 것은 아닙니다.</p>` + (window.trlNews || []).slice(0,3).map(row => {
      const timing = TRLFlow.newsTiming(row);
      return `<p><small>${esc(row.src)} · 발행 ${clock(timing.published)} · 수집 ${clock(timing.received)}</small><br>${esc(row.text)}<br><small>${timing.collectSeconds === null ? '발행→수집 시간 미확인' : '발행→수집 ' + timing.collectSeconds.toFixed(1) + '초'} · ${row.verify === 'official' ? '공식 출처' : row.verify === 'multi' ? '복수 보도' : '단일·미확인'}</small></p>`;
    }).join('');
  }
  window.addEventListener('trl:quotes', render);
  window.addEventListener('trl:news', render);
  setInterval(() => { if (!document.hidden) render(); }, 5000);
  render();
})();
