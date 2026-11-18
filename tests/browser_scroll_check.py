"""Chromium 실제 레이아웃 검사. 외부 시세·뉴스 호출 없음."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/"viewport.js").read_text(encoding="utf-8")
FOLD=(ROOT/"fold.js").read_text(encoding="utf-8")
TINT=(ROOT/"tint.js").read_text(encoding="utf-8")
CSS=(ROOT/"style.css").read_text(encoding="utf-8")
NEWS=(ROOT/"news.js").read_text(encoding="utf-8")
assert "setTimeout(apply, 120)" not in FOLD
assert "setInterval(apply, 15000)" not in FOLD
assert "spotTimer = setInterval" not in NEWS
assert "location.reload()" not in NEWS
assert "location.reload()" not in (ROOT/"pwa.js").read_text(encoding="utf-8")
FIXTURE="""<!doctype html><html><head></head><body><nav class="nav">TRL</nav><div id="top"></div>
<section id="chan"><div id="chanBoard"><div class="ch-country"></div></div></section>
<section id="tgSum"><details><summary>뉴스 원문 3건</summary><p style="height:200px">펼친 내용</p></details></section>
<section id="flowBox"><div class="fl-scroll"><div class="wide">가로 표</div></div></section>
<section id="news"><ul id="newsList"></ul></section><div id="tail"></div></body></html>"""
with sync_playwright() as p:
    browser=p.chromium.launch()
    for width in (390,1280):
        page=browser.new_page(viewport={"width":width,"height":900})
        page.route("**/*",lambda route:route.abort())
        page.set_content(FIXTURE)
        page.add_style_tag(content=CSS)
        page.add_style_tag(content="body{margin:0}.nav{position:fixed;top:0;height:60px;width:100%;z-index:10}#top{height:400px}.ch-card{height:200px}#newsList li{height:100px}#tail{height:2000px}.fl-scroll{width:240px;overflow:auto}.wide{width:1200px;height:50px}")
        page.evaluate("""() => {
          document.querySelector('.ch-country').innerHTML=Array.from({length:24},(_,i)=>'<article class="ch-card" data-viewport-key="channel:'+i+'">종목 '+i+'</article>').join('');
          document.querySelector('#newsList').innerHTML=Array.from({length:20},(_,i)=>'<li data-ts="'+(1000+i)+'">읽는 뉴스 '+i+'</li>').join('');
        }""")
        page.add_script_tag(content=CORE)
        page.add_script_tag(content=FOLD)
        page.add_script_tag(content=TINT)
        page.wait_for_timeout(100)
        page.evaluate("""() => {
          document.querySelector('details').open=true;
          document.querySelector('.fl-scroll').scrollLeft=220;
          const target=document.querySelector('[data-ts="1002"]');
          window.scrollTo({top:target.getBoundingClientRect().top+scrollY-120,behavior:'instant'});
        }""")
        page.wait_for_timeout(100)
        before=page.locator('[data-ts="1002"]').bounding_box()["y"]
        page.evaluate("""() => window.trlViewport.update(() => {
          document.querySelector('#top').style.height='650px';
          document.querySelector('#chanBoard').innerHTML='<div class="ch-country">'+Array.from({length:40},(_,i)=>'<article class="ch-card" data-viewport-key="channel:'+i+'">갱신 종목 '+i+'</article>').join('')+'</div>';
          document.querySelector('#tgSum').innerHTML='<details><summary>뉴스 원문 3건</summary><p style="height:200px">새 내용</p></details>';
          document.querySelector('#flowBox').innerHTML='<div class="fl-scroll"><div class="wide">새 가로 표</div></div>';
        })""")
        samples=page.evaluate("""() => new Promise(resolve => {
          const values=[];let n=0;
          function tick(){values.push(document.querySelector('[data-ts="1002"]').getBoundingClientRect().top);if(++n<12)requestAnimationFrame(tick);else resolve(values);}
          tick();
        })""")
        assert max(abs(y-before) for y in samples)<2,(width,before,samples)
        assert page.locator("details").evaluate("(el)=>el.open")
        assert page.locator(".fl-scroll").evaluate("(el)=>el.scrollLeft")==220
        page.evaluate("window.__foldButton=document.querySelector('[data-fold]')")
        pos=page.locator('[data-ts="1002"]').bounding_box()["y"]
        page.evaluate("() => {for(let i=0;i<8;i++)window.trlFold.apply();}")
        assert page.evaluate("window.__foldButton===document.querySelector('[data-fold]')")
        assert abs(page.locator('[data-ts="1002"]').bounding_box()["y"]-pos)<2
        page.evaluate("""() => window.trlViewport.update(() => {
          document.querySelector('#chanBoard').innerHTML='<div class="ch-country">'+Array.from({length:60},(_,i)=>'<article class="ch-card" data-viewport-key="channel:'+i+'">추가 종목 '+i+'</article>').join('')+'</div>';
        })""")
        page.wait_for_timeout(250)
        assert abs(page.locator('[data-ts="1002"]').bounding_box()["y"]-before)<2
        page.evaluate("window.trlViewport.offerUpdate();window.trlViewport.offerUpdate();")
        assert page.locator("#trlUpdateButton").count()==1
        assert abs(page.locator('[data-ts="1002"]').bounding_box()["y"]-before)<2
        print(f"viewport {width}: anchor, frames, details, horizontal table, idempotent folds, update notice PASS")
        page.close()
    browser.close()
