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
  function update(fn) {
    if(depth) return fn();
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
  window.trlViewport={update,html,offerUpdate,get updating(){return depth>0;}};
})();
