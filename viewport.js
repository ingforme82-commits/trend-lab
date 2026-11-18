/* 자동 갱신은 읽는 항목·펼침·표 가로 위치를 보존하는 동기 작업으로 처리한다. */
(() => {
  "use strict";
  let depth = 0, release = 0;
  const root = document.documentElement;
  const selectors = "[data-viewport-key],[data-ts],[data-start],section[id],[id]";
  const keyOf = (el) => el.hasAttribute("data-viewport-key") ? ["data-viewport-key",el.getAttribute("data-viewport-key")]
    : el.hasAttribute("data-ts") ? ["data-ts",el.getAttribute("data-ts")]
    : el.hasAttribute("data-start") ? ["data-start",el.getAttribute("data-start")]
    : el.id ? ["id",el.id] : null;
  const locate = (key) => key?.[0] === "id" ? document.getElementById(key[1])
    : key ? document.querySelector("["+key[0]+'="'+CSS.escape(key[1])+'"]') : null;
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
  function hold(){
    if(!lock)return;
    if(!lock.el.isConnected||performance.now()>lock.until){lock=null;return;}
    const want=navH()+8, d=lock.el.getBoundingClientRect().top-want;
    if(Math.abs(d)>1)jump(scrollY+d);
    lockRaf=requestAnimationFrame(hold);
  }
  function go(el,ms=2500){
    if(!el)return;
    lock={el,until:performance.now()+ms};
    root.classList.add("trl-live-update");
    jump(scrollY+el.getBoundingClientRect().top-(navH()+8));
    cancelAnimationFrame(lockRaf);lockRaf=requestAnimationFrame(hold);
    setTimeout(()=>{if(!lock)root.classList.remove("trl-live-update");},ms+50);
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
    if(lock&&lock.el.isConnected){             // 이동 고정 중: 그 항목 기준으로만 위치를 맞춘다
      depth++;root.classList.add("trl-live-update");
      try{const r=fn();window.trlFold?.apply();const d=lock.el.getBoundingClientRect().top-(navH()+8);if(Math.abs(d)>1)jump(scrollY+d);return r;}
      finally{depth--;}
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
  window.trlViewport={update,html,offerUpdate,go,get updating(){return depth>0;}};
})();
