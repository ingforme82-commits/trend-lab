"""뉴스 제목 자동 번역. 원문/시각/출처 보존, 캐시·재시도·무료 호출 예산.
Google 공개 번역은 비공식 경로이므로 실패 가능. MyMemory는 익명 일일
5000자보다 낮은 4800자만 사용한다. 별도 유료 API/LLM을 호출하지 않는다.
"""
from __future__ import annotations
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

POLICY = "ko-headlines-v1"
GOOGLE = "https://translate.googleapis.com/translate_a/single"
MEMORY = "https://api.mymemory.translated.net/get"
MAX_CALLS = 8
MAX_SECONDS = 20
MEMORY_CHARS = 4800
UA = {"User-Agent": "Mozilla/5.0"}


def needs_translation(item):
    text = str(item.get("orig") or item.get("text") or "").strip()
    latin = len(re.findall(r"[A-Za-z]", text))
    hangul = len(re.findall(r"[가-힣]", text))
    if item.get("lang") == "en":
        return latin >= 8 and (not hangul or latin > hangul * 2)
    return latin >= 20 and len(re.findall(r"[A-Za-z]{2,}", text)) >= 4 and latin > hangul * 3


def valid_translation(original, translated):
    if not isinstance(translated, str):
        return False
    text = html.unescape(translated).strip()
    if text.lower() == original.strip().lower() or not re.search(r"[가-힣]", text):
        return False
    if re.search(r"MYMEMORY WARNING|QUERY LENGTH LIMIT|USED ALL AVAILABLE FREE|TOO MANY REQUESTS|<html", text, re.I):
        return False
    return 2 <= len(text) <= max(1000, len(original) * 8)


def _get(url):
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=6) as response:
        body = response.read(200_001)
    if len(body) > 200_000:
        raise ValueError("translation response too large")
    return json.loads(body)


def google_batch(titles):
    # Identifiers must survive translation exactly; otherwise reject the batch,
    # never attach one article's translation to another article.
    text = "\n".join(f"__TRL_{i}__ "+t.replace("\n"," ") for i,t in enumerate(titles))
    url = GOOGLE + "?" + urllib.parse.urlencode({"client":"gtx","sl":"auto","tl":"ko","dt":"t","q":text})
    raw = _get(url)
    output = "".join(part[0] for part in raw[0] if part and isinstance(part[0],str))
    matches = list(re.finditer(r"__TRL_(\d+)__",output))
    if [int(m.group(1)) for m in matches] != list(range(len(titles))):
        raise ValueError("translation batch identifiers changed")
    result={}
    for i, match in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(output)
        value=output[match.end():end].strip()
        if valid_translation(titles[i],value):
            result[titles[i]]=html.unescape(value)
    return result


def memory_one(text):
    if len(text.encode("utf-8")) > 450:
        return None
    raw=_get(MEMORY+"?"+urllib.parse.urlencode({"q":text,"langpair":"en|ko"}))
    if str(raw.get("responseStatus")) != "200":
        raise ValueError("translation service declined")
    value=(raw.get("responseData") or {}).get("translatedText")
    return html.unescape(value) if valid_translation(text,value) else None


def _load(path):
    try:
        raw=json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw,dict) else {}
    except (OSError,ValueError): return {}


def _save(path,cache):
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache,ensure_ascii=False),encoding="utf-8")
        tmp.replace(path)
    except OSError: pass


def run(items, *, path: Path, legacy_path=None, terms=lambda en,ko:ko, now=None):
    now=time.time() if now is None else now
    started=time.monotonic()
    cache=_load(path)
    entries=cache.get("entries") or {}
    if cache.get("policy") != POLICY:
        entries={}
    if legacy_path and not entries:
        for original,value in _load(legacy_path).items():
            if not original.startswith("_") and valid_translation(original,value):
                entries[original]={"text":value,"provider":"legacy","at":now}
    retry=cache.get("retry") or {}
    budget=cache.get("budget") or {}
    if not 0 <= now-budget.get("start",0) < 60:
        budget={"start":now,"calls":0}
    memory=cache.get("memory") or {}
    day=time.strftime("%Y-%m-%d",time.gmtime(now))
    if memory.get("day")!=day: memory={"day":day,"chars":0}
    off=cache.get("off") or {}
    errors={}
    attempted=set()
    stats={"policy":POLICY,"providers":{},"attempted_titles":0,"translated":0,"pending":0,"errors":errors}

    def available():
        return budget.get("calls",0)<MAX_CALLS and time.monotonic()-started<MAX_SECONDS

    def error(provider,exc):
        code="HTTP_"+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__
        errors[provider+":"+code]=errors.get(provider+":"+code,0)+1
        # Global source backoff; do not evade a rate limit via alternate domains.
        off[provider]=now+(600 if code in ("HTTP_429","HTTP_403") else 60)

    originals={}
    for item in items:
        if not needs_translation(item): continue
        original=str(item.get("orig") or item["text"]).strip()
        if item.get("tr")=="auto" and valid_translation(original,item.get("text")):
            entries.setdefault(original,{"text":item["text"],"provider":item.get("tr_provider","legacy"),"at":now})
        originals[original]=max(originals.get(original,0),item.get("ts",0))
    todo=[text for text in sorted(originals,key=lambda t:-originals[t])
          if not valid_translation(text,(entries.get(text) or {}).get("text")) and retry.get(text,0)<=now]
    # At most six titles per request and a bounded encoded URL.
    pending=list(todo)
    while pending and available() and off.get("google",0)<=now:
        batch=[]
        while pending and len(batch)<6 and sum(len(t.encode("utf-8")) for t in batch)<1000:
            batch.append(pending.pop(0))
        budget["calls"]=budget.get("calls",0)+1
        attempted.update(batch)
        stats["attempted_titles"]+=len(batch)
        try:
            got=google_batch(batch)
            for text,value in got.items():
                entries[text]={"text":value,"provider":"google","at":now}
            if not got: error("google",ValueError())
        except Exception as exc:
            error("google",exc)
    # A small fallback queue within the anonymous provider's documented daily cap.
    for text in todo:
        if not available() or off.get("mymemory",0)>now: break
        if valid_translation(text,(entries.get(text) or {}).get("text")): continue
        if len(text.encode("utf-8"))>450 or memory.get("chars",0)+len(text)>MEMORY_CHARS: continue
        memory["chars"]=memory.get("chars",0)+len(text)
        budget["calls"]=budget.get("calls",0)+1
        attempted.add(text)
        stats["attempted_titles"]+=1
        try:
            value=memory_one(text)
            if value: entries[text]={"text":value,"provider":"mymemory","at":now}
            else: error("mymemory",ValueError())
        except Exception as exc:
            error("mymemory",exc)
    for item in items:
        if not needs_translation(item): continue
        original=str(item.get("orig") or item["text"]).strip()
        entry=entries.get(original) or {}
        translated=entry.get("text")
        item["orig"]=original
        item["lang"]="en" if item.get("lang") is None else item["lang"]
        if valid_translation(original,translated):
            item["text"]=terms(original,translated.rstrip(".。 "))
            item["tr"]="auto";item["tr_provider"]=entry.get("provider","unknown")
            item["tr_status"]="translated"
            stats["translated"]+=1
            provider=item["tr_provider"];stats["providers"][provider]=stats["providers"].get(provider,0)+1
            retry.pop(original,None)
        else:
            item["text"]=original;item["tr"]="fail";item["tr_status"]="retry_pending"
            retry[original]=now+60 if original in attempted else retry.get(original,0)
            stats["pending"]+=1
    entries={k:v for k,v in entries.items() if now-v.get("at",now)<7*86400}
    entries=dict(sorted(entries.items(),key=lambda kv:kv[1].get("at",0),reverse=True)[:5000])
    retry={k:v for k,v in retry.items() if k in originals}
    stats["provider_backoff_until"]={k:v for k,v in off.items() if v>now}
    stats["fallback_chars_today"]=memory.get("chars",0)
    _save(path,{"policy":POLICY,"entries":entries,"retry":retry,"budget":budget,"memory":memory,"off":off})
    return stats


def translate_one(text):
    import keystore
    item={"text":text,"lang":"en","ts":0}
    run([item],path=keystore.state_dir()/"news_translation.json")
    return item["text"] if item.get("tr")=="auto" else ""
