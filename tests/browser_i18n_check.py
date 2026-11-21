"""Chromium 실제 화면 번역 점검(2026-11-21) — 자동 번역 서버를 막은 상태에서 사이트 고정 문구에 한글이 남는지 본다.

  python tests/browser_i18n_check.py            # en ja zh-hans zh-hant fr × index·study
  TRL_NEWS_JSON=경로 python tests/browser_i18n_check.py   # 속보 데이터까지 채워서(라이브 news.json 사본)

외부 호출은 모두 막는다(번역·시세·카운터). 속보·스터디 본문 같은 '데이터' 칸은 자동 번역(재시도 포함) 몫이라 제외하고,
그 밖의 머리·메뉴·버튼·안내·바닥 글은 i18n-ui.js 사전만으로 한 글자도 남지 않아야 통과.
"""
import functools, http.server, json, os, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
import time
NEWS = Path(os.environ["TRL_NEWS_JSON"]).read_bytes() if os.environ.get("TRL_NEWS_JSON") else json.dumps({"items": [], "updated": int(time.time() * 1000)}).encode()
DATA = ("#newsList,#moveList,#tgSum,#heroLive,#ticker,#notice,#hlList,#chanBoard,#chanSig,#s7Box,#watchBox,#sectorBox,#flowBox,"
        "#briefNow,#newsCharts,#trendBox,#checkList,#archList,#eduList,#upList,#studyInfo,#curList,#bookList,#worldGrid,#srcScoreBody,"
        "#moveReact,#heroStudy,#archStats,#archChips,#newsChips,#curNote,#curSub,#bookSub,#tickGrid,.quiz-box,#result,main.sec")
JS = """(DATA)=>{const H=/[가-힣]/,out=[];const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
for(let n=w.nextNode();n;n=w.nextNode()){const el=n.parentElement;if(el.closest('script,style,noscript,[translate=no],#trlLanguage'))continue;
const t=n.data.trim();if(t&&H.test(t)&&!el.closest(DATA))out.push(t.slice(0,80))}
document.querySelectorAll('[title],[aria-label],[placeholder],[alt]').forEach(e=>{if(e.closest(DATA)||e.closest('#trlLanguage,[translate=no]'))return;
for(const a of ['title','aria-label','placeholder','alt']){const v=e.getAttribute(a);if(v&&H.test(v))out.push('@'+a+': '+v.slice(0,60))}});return [...new Set(out)]}"""

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT)))
srv.RequestHandlerClass.log_message = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/"


def route(r):
    u = r.request.url
    if u.startswith(base):
        return r.continue_()
    if "news.json" in u:
        return r.fulfill(body=NEWS, content_type="application/json")
    return r.abort()


fails = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for lang in ("en", "ja", "zh-hans", "zh-hant", "fr"):
        for page in ("index.html?", "study.html?id=2026-11-14&"):
            ctx = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            pg = ctx.new_page()
            pg.route("**/*", route)
            pg.goto(f"{base}{page}lang={lang}", wait_until="load")
            pg.wait_for_timeout(9000)
            left = pg.evaluate(JS, DATA)
            if left:
                fails[f"{lang} {page.split('?')[0]}"] = left
            ctx.close()
    b.close()
srv.shutdown()
if fails:
    print(json.dumps(fails, ensure_ascii=False, indent=1))
    sys.exit("번역표(i18n-ui.js)에 없는 고정 문구가 있습니다")
print("ok — 5개 언어 × 2쪽, 고정 문구에 한글 없음")
