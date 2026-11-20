/* 자동 갱신은 읽는 항목·펼침·표 가로 위치를 보존하는 동기 작업으로 처리한다. */
(() => {
  "use strict";
  let depth = 0, release = 0;
  const root = document.documentElement;
  const selectors = "[data-viewport-key],[data-ts],[data-start],section[id],[id]";
  const keyOf = (el) => {
    const scope = el.parentElement?.closest("[id]")?.id || null;
    return el.hasAttribute("data-viewport-key") ? ["data-viewport-key", el.getAttribute("data-viewport-key"), scope]
      : el.hasAttribute("data-ts") ? ["data-ts", el.getAttribute("data-ts"), scope]
      : el.hasAttribute("data-start") ? ["data-start", el.getAttribute("data-start"), scope]
      : el.id ? ["id", el.id] : null;
  };
  const locate = (key) => {
    if (!key) return null;
    if (key[0] === "id") return document.getElementById(key[1]);
    const owner = key[2] ? document.getElementById(key[2]) : document;
    return owner?.querySelector("["+key[0]+'="'+CSS.escape(key[1])+'"]') || null;
  };
  function anchor() {
    const probe = Math.min(innerHeight / 3, Math.max(80, (document.querySelector(".nav")?.getBoundingClientRect().bottom || 0) + 24));
    const point = document.elementFromPoint(innerWidth / 2, probe);
    const exact = point?.closest(selectors);
    if (exact && exact !== document.body && exact !== root && !exact.closest(".nav")) return {key:keyOf(exact),top:exact.getBoundingClientRect().top};
    const candidates = [...document.querySelectorAll("[data-viewport-key],[data-ts],[data-start],section[id]")];
    const visible = candidates.map(el=>({el,r:el.getBoundingClientRect()})).filter(x=>x.r.height>0&&x.r.bottom>probe&&x.r.top<innerHeight);
    visible.sort((a,b)=>Math.abs(a.r.top-probe)-Math.abs(b.r.top-probe));
    const best=visible[0];
    return best ? {key:keyOf(best.el),top:best.r.top} : null;
  }
  const detailKey = (el) => (el.closest("[id]")?.id || "") + "|" +
    (el.querySelector("summary")?.textContent || "").replace(/\d+건/g,"").replace(/\s+/g," ").trim();
  function state() {
    const details=new Map();
    document.querySelectorAll("details").forEach(el=>{const k=detailKey(el);const values=details.get(k)||[];values.push(el.open);details.set(k,values);});
    const horizontal=[];
    document.querySelectorAll(".fl-scroll,.band-items").forEach(el=>{
      const owner=el.closest("[id]");if(!owner||!el.scrollLeft)return;
      horizontal.push({id:owner.id,index:[...owner.querySelectorAll(".fl-scroll,.band-items")].indexOf(el),left:el.scrollLeft});
    });
    return {details,horizontal};
  }
  function restoreState(snapshot) {
    const seen=new Map();
    document.querySelectorAll("details").forEach(el=>{
      const k=detailKey(el),i=seen.get(k)||0;seen.set(k,i+1);
      if(snapshot.details.has(k)&&i<snapshot.details.get(k).length)el.open=snapshot.details.get(k)[i];
    });
    snapshot.horizontal.forEach(x=>{
      const el=document.getElementById(x.id)?.querySelectorAll(".fl-scroll,.band-items")[x.index];
      if(el)el.scrollLeft=x.left;
    });
  }
  /* ── 이동 고정(11/18 운영자 "속보 클릭해도 딱 고정이 안 됨") ──
   * 부드러운 스크롤 도중 1분·2초 자동 갱신이 위치를 다시 맞추면서 이동이 중간에 끊기고,
   * 위쪽 칸 높이가 바뀌면 도착 지점이 밀렸다. 그래서 클릭 이동은 즉시 이동 + 2.5초 동안 그 항목을
   * 메뉴 바로 아래에 붙잡아 둔다(갱신·접기·이미지 로딩으로 높이가 변해도 다시 맞춤). 손으로 스크롤하면 바로 풀린다. */
  let lock=null, lockRaf=0;
  const navH=()=>Math.ceil(document.querySelector(".nav")?.getBoundingClientRect().bottom||0);
  const jump=(top)=>{try{window.scrollTo({left:scrollX,top:Math.max(0,top),behavior:"instant"});}catch{window.scrollTo(scrollX,Math.max(0,top));}};
  function lockElement(){
    if(!lock)return null;
    if(!lock.el.isConnected)lock.el=locate(lock.key);
    return lock.el?.isConnected ? lock.el : null;
  }
  function hold(){
    if(!lock)return;
    const el=lockElement();
    if(!el||performance.now()>lock.until){unlock();return;}
    const want=navH()+8, d=el.getBoundingClientRect().top-want;
    if(Math.abs(d)>1)jump(scrollY+d);
    lockRaf=requestAnimationFrame(hold);
  }
  function go(el,ms=2500){
    if(!el)return;
    lock={el,key:keyOf(el),until:performance.now()+ms};
    root.classList.add("trl-live-update");
    jump(scrollY+el.getBoundingClientRect().top-(navH()+8));
    cancelAnimationFrame(lockRaf);lockRaf=requestAnimationFrame(hold);
    setTimeout(()=>{if(lock&&performance.now()>=lock.until)unlock();else if(!lock)root.classList.remove("trl-live-update");},ms+50);
  }
  const unlock=()=>{if(lock){lock=null;cancelAnimationFrame(lockRaf);root.classList.remove("trl-live-update");}};
  ["wheel","touchstart","keydown"].forEach((t)=>addEventListener(t,unlock,{passive:true}));
  // 같은 페이지 안 링크(#news 등)는 모두 즉시 이동 + 고정으로
  document.addEventListener("click",(e)=>{
    if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey)return;
    const a=e.target.closest('a[href^="#"]');if(!a)return;
    const id=decodeURIComponent(a.getAttribute("href").slice(1));const el=id?document.getElementById(id):null;if(!el)return;
    e.preventDefault();
    if(location.hash!=="#"+id)history.replaceState(null,"","#"+id);
    go(el);
  });
  function update(fn) {
    if(depth) return fn();
    if(lockElement()){
      const saved=state();
      depth++;root.classList.add("trl-live-update");
      try{
        const r=fn();restoreState(saved);window.trlFold?.apply();
        const el=lockElement();
        if(el){const d=el.getBoundingClientRect().top-(navH()+8);if(Math.abs(d)>1)jump(scrollY+d);}
        else unlock();
        return r;
      } finally{depth--;}
    }
    const mark=scrollY>80?anchor():null, beforeY=scrollY, beforeX=scrollX, saved=state();
    depth++;
    root.classList.add("trl-live-update");
    try {
      const result=fn();
      restoreState(saved);
      window.trlFold?.apply();
      const element=mark&&locate(mark.key);
      const delta=element&&element.getBoundingClientRect().height>0 ? element.getBoundingClientRect().top-mark.top : 0;
      const target=beforeY>80 ? Math.max(0,beforeY+delta) : beforeY;
      if(Math.abs(scrollY-target)>0.5) {
        try { window.scrollTo({left:beforeX,top:target,behavior:"instant"}); }
        catch { window.scrollTo(beforeX,target); }
      }
      return result;
    } finally {
      depth--;
      if(release)cancelAnimationFrame(release);
      release=requestAnimationFrame(()=>{release=requestAnimationFrame(()=>{root.classList.remove("trl-live-update");release=0;});});
    }
  }
  const lastHTML=new WeakMap();
  function html(el,value) {
    if(!el||lastHTML.get(el)===value)return false;
    return update(()=>{el.innerHTML=value;lastHTML.set(el,value);return true;});
  }
  function offerUpdate() {
    if(document.getElementById("trlUpdateButton"))return;
    const button=document.createElement("button");
    button.id="trlUpdateButton";button.type="button";button.className="btn btn-gold";
    button.textContent="새 버전 적용";button.title="읽던 내용을 마친 뒤 눌러 새 버전을 적용하세요";
    button.addEventListener("click",()=>location.reload());
    document.body.append(button);
  }
  /* ── 상시 위치 고정(11/20 운영자 "화면이 정지가 안 되고 살짝씩 움직임") ──
   * update() 밖에서 생기는 높이 변화(번역 치환·차트·이미지·2초 시세 글자 폭)도 읽던 항목을 제자리에 둔다.
   * 사파리는 브라우저 스크롤 고정(overflow-anchor)이 없어 직접 맞춘다. 손으로 스크롤하는 중(0.25초)엔 건드리지 않는다. */
  let pin=null, userAt=0, pinRaf=0, fixRaf=0;
  function pinNow(){
    pinRaf=0;
    if(scrollY<=80){pin=null;return;}
    const probe=Math.min(innerHeight/3,Math.max(80,navH()+24));
    let el=document.elementFromPoint(innerWidth/2,probe);
    if(!el||el===document.body||el===root||el.closest(".nav")){const a=anchor();pin=a&&{el:locate(a.key),key:a.key,top:a.top};return;}
    const keyed=el.closest(selectors);
    pin={el,key:keyed&&keyed!==document.body?keyOf(keyed):null,keyed,top:el.getBoundingClientRect().top,ktop:keyed?.getBoundingClientRect().top};
  }
  function fix(){
    fixRaf=0;
    if(!pin||depth||lock||performance.now()-userAt<250)return;
    let d=null;
    if(pin.el?.isConnected&&pin.el.getBoundingClientRect().height>0)d=pin.el.getBoundingClientRect().top-pin.top;
    else{const k=locate(pin.key);if(k)d=k.getBoundingClientRect().top-(pin.ktop??pin.top);}
    if(d!=null&&Math.abs(d)>0.5){jump(scrollY+d);}
    pinNow();
  }
  ["wheel","touchstart","touchmove","keydown","pointerdown"].forEach((t)=>addEventListener(t,()=>{userAt=performance.now();},{passive:true}));
  addEventListener("scroll",()=>{if(!pinRaf)pinRaf=requestAnimationFrame(pinNow);},{passive:true});
  addEventListener("resize",()=>{pin=null;pinRaf=requestAnimationFrame(pinNow);});
  if(window.ResizeObserver){
    const ro=new ResizeObserver(()=>{if(!fixRaf)fixRaf=requestAnimationFrame(fix);});
    const watch=()=>{ro.observe(document.body);document.querySelectorAll("body > *, main > *, section").forEach((el)=>ro.observe(el));};
    if(document.readyState==="loading")addEventListener("DOMContentLoaded",watch);else watch();
  }
  const baseUpdate=update;
  function updatePinned(fn){try{return baseUpdate(fn);}finally{if(!depth){if(pinRaf)cancelAnimationFrame(pinRaf);pinRaf=requestAnimationFrame(pinNow);}}}
  window.trlViewport={update:updatePinned,html:(el,value)=>{if(!el||lastHTML.get(el)===value)return false;return updatePinned(()=>{el.innerHTML=value;lastHTML.set(el,value);return true;});},offerUpdate,go,get updating(){return depth>0;}};
})();
