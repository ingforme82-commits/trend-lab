"""Chromium 실제 레이아웃: update() 밖에서 위쪽 높이가 바뀌어도(번역 치환·차트·이미지) 읽던 항목이 제자리인지(11/20 운영자 "화면이 살짝씩 움직임").
사파리처럼 브라우저 스크롤 고정이 없는 상황을 overflow-anchor:none 으로 흉내 낸다. 외부 호출 없음."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "viewport.js").read_text(encoding="utf-8")
FIXTURE = """<!doctype html><html><head><style>
*{overflow-anchor:none}body{margin:0}.nav{position:fixed;top:0;height:60px;width:100%;background:#123;z-index:9}
#top{height:400px}#grow{height:100px}#list li{height:100px}#tail{height:3000px}
</style></head><body><nav class="nav">TRL</nav><div id="top"></div><section id="hero"><div id="grow">위쪽 칸</div></section>
<section id="news"><ul id="list">""" + "".join(f'<li data-ts="{i}">뉴스 {i}</li>' for i in range(30)) + """</ul></section><div id="tail"></div></body></html>"""

with sync_playwright() as p:
    b = p.chromium.launch()
    for w in (390, 1280):
        pg = b.new_page(viewport={"width": w, "height": 900})
        pg.route("**/*", lambda r: r.abort())
        pg.set_content(FIXTURE)
        pg.add_script_tag(content=CORE)
        pg.evaluate("window.scrollTo(0, document.querySelector('[data-ts=\"10\"]').offsetTop - 200)")
        pg.wait_for_timeout(400)                       # 고정점 잡기(스크롤 뒤 다음 프레임)
        top = lambda: pg.evaluate("document.querySelector('[data-ts=\"10\"]').getBoundingClientRect().top")
        t0 = top()
        # ① update() 밖에서 위쪽 칸이 커짐(차트·번역)
        pg.evaluate("document.getElementById('grow').style.height='420px'")
        pg.wait_for_timeout(200)
        assert abs(top() - t0) <= 1, (w, "위쪽 칸이 커져도 제자리", t0, top())
        # ② 위쪽 칸이 줄어듦
        pg.evaluate("document.getElementById('grow').style.height='40px'")
        pg.wait_for_timeout(200)
        assert abs(top() - t0) <= 1, (w, "위쪽 칸이 줄어도 제자리", t0, top())
        # ③ 목록 통째 교체(innerHTML) + 위에 새 뉴스 3개 — 같은 data-ts 항목을 따라간다
        pg.evaluate("""() => { const ul=document.getElementById('list');
          ul.innerHTML = ['a','b','c'].map(x=>`<li data-ts="n${x}">새 뉴스</li>`).join('') + ul.innerHTML; }""")
        pg.wait_for_timeout(200)
        assert abs(top() - t0) <= 1, (w, "목록 교체 뒤에도 같은 항목", t0, top())
        # ④ 손으로 스크롤하는 중에는 끌어당기지 않는다
        pg.mouse.move(w / 2, 400)
        pg.mouse.wheel(0, 300)
        pg.wait_for_timeout(50)
        y = pg.evaluate("scrollY")
        pg.evaluate("document.getElementById('grow').style.height='300px'")
        pg.wait_for_timeout(30)
        assert abs(pg.evaluate("scrollY") - y) <= 1, (w, "사용자 스크롤 중 보정 금지")
        print(f"steady {w}: grow, shrink, list replace, user scroll PASS")
    b.close()
