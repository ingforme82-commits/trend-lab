"""📒 가치 투자 성장 스토리 — 개인 공부 사진(운영자 외 얼굴 모자이크) 만들기. 원본은 저장소에 절대 넣지 않는다.

  python tools/growth_photos.py detect "C:\\조영근\\추세 추종 스터디 사진\\가치투자 스터디 3년 3종류"
      → 얼굴을 찾아 작업 파일(boxes.json)에 저장. 원본 폴더 옆 '가치투자_모자이크_작업' 폴더(저장소 밖)
  python tools/growth_photos.py review "같은 폴더"
      → 내 PC에서만 열리는 확인 페이지(http://127.0.0.1:8765). 빨간 상자 = 모자이크, 누르면 초록(본인, 모자이크 안 함)
        빈 곳을 끌면 상자 추가(놓친 얼굴·이름 글자), 상자의 ✕ = 삭제, '올리지 않기' 체크 = 사진 제외. 바뀔 때마다 자동 저장
  python tools/growth_photos.py apply "같은 폴더" [--push]
      → 모자이크한 사진을 study/growth/ 에 만들고 data/growth.json 갱신(메타데이터 없이 저장)

- 기본값은 '모든 얼굴 모자이크'. 운영자가 직접 누른 얼굴만 풀린다.
- 모자이크는 되돌릴 수 없게(상자를 넓혀서 큰 칸으로 뭉갠 뒤 흐림) 만든 사진만 저장소에 들어간다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "study" / "growth"
DATA = ROOT / "data" / "growth.json"
CV = ROOT / "tools" / ".cv"
TITLE = "가치 투자 성장 스토리"
INTRO = ("운영자가 2024년 2월부터 참여해 온 텔레그램 가치투자 스터디의 개인 공부 기록입니다. 사진이 남아 있는 날짜 순으로 모았습니다. "
         "운영자를 제외한 참석자 얼굴은 모두 모자이크 처리했습니다.")
SIZE = 1600


def work_dir(src: Path) -> Path:
    w = src.parent / "가치투자_모자이크_작업"
    w.mkdir(exist_ok=True)
    return w


def date_of(name: str) -> str:
    m = re.search(r"(20\d\d)-?(\d\d)-?(\d\d)", name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def photos(src: Path) -> list[Path]:
    return sorted((p for p in src.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")), key=lambda p: (date_of(p.name), p.name))


def _read(p: Path):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    with Image.open(p) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


# ── 순수 함수(tests/test_growth_photos.py) ──
def iou(a: dict, b: dict) -> float:
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2, y2 = min(a["x"] + a["w"], b["x"] + b["w"]), min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / float(a["w"] * a["h"] + b["w"] * b["h"] - inter or 1)


def merge_boxes(boxes: list[dict], thr: float = 0.3) -> list[dict]:
    """겹치는 상자는 하나로(둘을 감싸는 상자)."""
    out: list[dict] = []
    for b in sorted(boxes, key=lambda b: -b["w"] * b["h"]):
        for o in out:
            if iou(o, b) > thr or (b["x"] >= o["x"] and b["y"] >= o["y"] and b["x"] + b["w"] <= o["x"] + o["w"] and b["y"] + b["h"] <= o["y"] + o["h"]):
                x1, y1 = min(o["x"], b["x"]), min(o["y"], b["y"])
                o.update(x=x1, y=y1, w=max(o["x"] + o["w"], b["x"] + b["w"]) - x1, h=max(o["y"] + o["h"], b["y"] + b["h"]) - y1)
                break
        else:
            out.append(dict(b))
    return out


def grow(b: dict, W: int, H: int) -> tuple[int, int, int, int]:
    """머리카락·귀·턱까지 덮도록 상자를 넓힌다(좌우·아래 25%, 위 35% — 가로세로 60px 미만 작은 얼굴은 45%·55%)."""
    k = 0.25 if max(b["w"], b["h"]) >= 60 else 0.45            # 작은 얼굴은 더 넓게
    x0 = max(0, int(b["x"] - b["w"] * k))
    y0 = max(0, int(b["y"] - b["h"] * (k + 0.1)))
    x1 = min(W, int(b["x"] + b["w"] * (1 + k)))
    y1 = min(H, int(b["y"] + b["h"] * (1 + k)))
    return x0, y0, x1, y1


def mosaic(img, boxes: list[dict]):
    """keep(본인)이 아닌 상자를 큰 칸 모자이크 + 흐림으로 덮는다. src='me' 상자(본인 얼굴)는 다른 사람 모자이크가 덮지 않게 원본으로 되돌린다."""
    import cv2
    H, W = img.shape[:2]
    out = img.copy()
    me = [protect(b, W, H) for b in boxes if b.get("src") == "me"]
    for b in boxes:
        if b.get("keep"):
            continue
        x0, y0, x1, y1 = grow(b, W, H) if b.get("src") != "manual" else (max(0, b["x"]), max(0, b["y"]), min(W, b["x"] + b["w"]), min(H, b["y"] + b["h"]))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        roi = out[y0:y1, x0:x1]
        cell = max(5, int(max(x1 - x0, y1 - y0) / 6))
        small = cv2.resize(roi, (max(1, (x1 - x0) // cell), max(1, (y1 - y0) // cell)), interpolation=cv2.INTER_AREA)
        px = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        out[y0:y1, x0:x1] = cv2.GaussianBlur(px, (0, 0), cell / 3)
    if not me:
        return out
    for x0, y0, x1, y1 in me:                                   # 본인 얼굴·머리는 원본 그대로(넓힌 모자이크 가장자리만 걷힘)
        out[y0:y1, x0:x1] = img[y0:y1, x0:x1]
    for b in boxes:                                             # 다른 사람 얼굴 자체는 마지막에 다시 덮는다(본인 보호보다 우선)
        if b.get("keep"):
            continue
        cx0, cy0 = max(0, int(b["x"] - b["w"] * 0.1)), max(0, int(b["y"] - b["h"] * 0.15))
        cx1, cy1 = min(W, int(b["x"] + b["w"] * 1.1)), min(H, int(b["y"] + b["h"] * 1.1))
        if any(cx0 < x1 and x0 < cx1 and cy0 < y1 and y0 < cy1 for x0, y0, x1, y1 in me):
            cell = max(5, int(max(cx1 - cx0, cy1 - cy0) / 6))
            roi = img[cy0:cy1, cx0:cx1]
            small = cv2.resize(roi, (max(1, (cx1 - cx0) // cell), max(1, (cy1 - cy0) // cell)), interpolation=cv2.INTER_AREA)
            out[cy0:cy1, cx0:cx1] = cv2.GaussianBlur(cv2.resize(small, (cx1 - cx0, cy1 - cy0), interpolation=cv2.INTER_NEAREST), (0, 0), cell / 3)
    return out


def protect(b: dict, W: int, H: int) -> tuple[int, int, int, int]:
    """본인 얼굴 보호 영역: 좌우 12%, 위 30%(머리카락), 아래 12%."""
    return (max(0, int(b["x"] - b["w"] * 0.12)), max(0, int(b["y"] - b["h"] * 0.30)),
            min(W, int(b["x"] + b["w"] * 1.12)), min(H, int(b["y"] + b["h"] * 1.12)))


def finish(img, d: dict):
    """사진 단위 보정: enhance(밝기·대비 살짝, 선명하게), crop([x, y, w, h] 원본 좌표)."""
    from PIL import ImageEnhance, ImageOps
    if d.get("crop"):
        x, y, w, h = d["crop"]
        img = img.crop((x, y, x + w, y + h))
    if d.get("enhance"):
        img = ImageOps.autocontrast(img, cutoff=0.5)
        img = ImageEnhance.Brightness(img).enhance(1.04)
        img = ImageEnhance.Sharpness(img).enhance(1.25)
    return img


# ── 명령 ──
def detect(src: Path) -> None:
    import cv2
    casc = {n: cv2.CascadeClassifier(str(CV / f"haarcascade_{n}.xml")) for n in ("frontalface_default", "frontalface_alt2", "profileface")}
    yn = cv2.FaceDetectorYN.create(str(CV / "face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.45, 0.3, 5000)   # OpenCV YuNet(위치만 찾음)
    if any(c.empty() for c in casc.values()):
        raise SystemExit("얼굴 데이터 파일을 못 읽었습니다(tools/.cv). OpenCV 4.x 설치 후 다시 복사하세요.")
    wf = work_dir(src) / "boxes.json"
    old = json.loads(wf.read_text(encoding="utf-8")) if wf.exists() else {}
    data = {}
    for p in photos(src):
        if p.name in old and old[p.name].get("edited"):
            data[p.name] = old[p.name]                         # 이미 손본 사진은 그대로 둔다
            continue
        img = _read(p)
        H, W = img.shape[:2]
        raw = []
        for sc in (1.0, 2.0):                                   # 2배로 키워 작은 얼굴도
            im2 = cv2.resize(img, (int(W * sc), int(H * sc))) if sc != 1 else img
            yn.setInputSize((im2.shape[1], im2.shape[0]))
            _, faces = yn.detect(im2)
            for f in (faces if faces is not None else []):
                raw.append(tuple(int(v / sc) for v in f[:4]))
        g = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        mn = max(18, min(W, H) // 40)
        for n in ("frontalface_default", "frontalface_alt2"):  # 보조: 정면 얼굴
            raw += [tuple(map(int, b)) for b in casc[n].detectMultiScale(g, 1.07, 6, minSize=(mn, mn))]
        boxes = merge_boxes([{"x": x, "y": y, "w": w, "h": h, "keep": False, "src": "auto"} for x, y, w, h in raw])
        data[p.name] = {"date": date_of(p.name), "W": W, "H": H, "boxes": boxes, "skip": False, "edited": False}
        print(f"{p.name}: 얼굴 후보 {len(boxes)}개")
    wf.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {wf}")


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>모자이크 확인</title>
<style>body{font-family:system-ui,'Malgun Gothic';margin:0;background:#f4f5f7;color:#222}header{position:sticky;top:0;background:#1d2433;color:#fff;padding:10px 16px;z-index:9}
header b{margin-right:12px}header label{margin-left:12px}.ph{background:#fff;margin:14px auto;max-width:1100px;padding:10px;border-radius:10px}
.ph h3{margin:0 0 6px;font-size:15px}.st{position:relative;display:inline-block;max-width:100%;cursor:crosshair;user-select:none}.st img{max-width:100%;display:block}
.bx{position:absolute;border:3px solid #e33;background:rgba(230,50,50,.12);cursor:pointer}.bx.keep{border-color:#1a9e4b;background:rgba(26,158,75,.12)}
.bx i{position:absolute;right:-10px;top:-12px;background:#222;color:#fff;font-style:normal;font-size:12px;border-radius:50%;width:20px;height:20px;text-align:center;line-height:20px}
.bx.keep::after{content:'본인';position:absolute;left:0;top:-20px;background:#1a9e4b;color:#fff;font-size:12px;padding:1px 5px}
.skip{opacity:.35}.drag{position:absolute;border:2px dashed #e33}small{color:#666}</style></head><body>
<header><b>모자이크 확인</b><small style="color:#cfd6e4">빨강=모자이크 · 누르면 초록(본인) · 빈 곳 끌기=상자 추가 · ✕=삭제 · 자동 저장</small>
<label><input type="checkbox" id="pv"> 결과 미리보기</label> <span id="msg"></span></header><main id="m"></main>
<script>
let D={};const m=document.getElementById('m');
const save=async()=>{const r=await fetch('/save',{method:'POST',body:JSON.stringify(D)});document.getElementById('msg').textContent=r.ok?'저장됨 '+new Date().toLocaleTimeString():'저장 실패';};
function draw(){const pv=document.getElementById('pv').checked;m.innerHTML='';
 Object.entries(D).forEach(([f,d])=>{const sec=document.createElement('section');sec.className='ph'+(d.skip?' skip':'');
  const n=d.boxes.filter(b=>!b.keep).length,k=d.boxes.filter(b=>b.keep).length;
  sec.innerHTML=`<h3>${d.date} <small>${f} · 모자이크 ${n} · 본인 ${k}</small> <label style="float:right"><input type="checkbox" ${d.skip?'checked':''} data-skip> 올리지 않기</label></h3>`;
  const st=document.createElement('div');st.className='st';const img=new Image();img.src=(pv?'/preview/':'/img/')+encodeURIComponent(f)+'?t='+Date.now();st.appendChild(img);sec.appendChild(st);m.appendChild(sec);
  sec.querySelector('[data-skip]').onchange=e=>{d.skip=e.target.checked;d.edited=true;save();draw();};
  if(pv)return;
  img.onload=()=>{const s=img.clientWidth/d.W;
   d.boxes.forEach((b,i)=>{const e=document.createElement('div');e.className='bx'+(b.keep?' keep':'');Object.assign(e.style,{left:b.x*s+'px',top:b.y*s+'px',width:b.w*s+'px',height:b.h*s+'px'});
    e.innerHTML='<i>✕</i>';e.onmousedown=ev=>ev.stopPropagation();
    e.onclick=ev=>{ev.stopPropagation();if(ev.target.tagName==='I'){d.boxes.splice(i,1);}else{b.keep=!b.keep;}d.edited=true;save();draw();};st.appendChild(e);});
   let o=null,dv=null;st.onmousedown=ev=>{const r=st.getBoundingClientRect();o=[ev.clientX-r.left,ev.clientY-r.top];dv=document.createElement('div');dv.className='drag';st.appendChild(dv);ev.preventDefault();};
   st.onmousemove=ev=>{if(!o)return;const r=st.getBoundingClientRect(),x=ev.clientX-r.left,y=ev.clientY-r.top;Object.assign(dv.style,{left:Math.min(x,o[0])+'px',top:Math.min(y,o[1])+'px',width:Math.abs(x-o[0])+'px',height:Math.abs(y-o[1])+'px'});};
   st.onmouseup=ev=>{if(!o)return;const r=st.getBoundingClientRect(),x=ev.clientX-r.left,y=ev.clientY-r.top;const w=Math.abs(x-o[0]),h=Math.abs(y-o[1]);
    if(w>6&&h>6){d.boxes.push({x:Math.round(Math.min(x,o[0])/s),y:Math.round(Math.min(y,o[1])/s),w:Math.round(w/s),h:Math.round(h/s),keep:false,src:'manual'});d.edited=true;save();}o=null;draw();};};
 });}
document.getElementById('pv').onchange=draw;
fetch('/boxes').then(r=>r.json()).then(j=>{D=j;draw();});
</script></body></html>"""


def review(src: Path, port: int = 8765) -> None:
    import cv2
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import unquote, urlparse
    wf = work_dir(src) / "boxes.json"
    if not wf.exists():
        raise SystemExit("먼저 detect 를 실행하세요")

    class H(BaseHTTPRequestHandler):
        def _send(self, body: bytes, ctype: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # noqa: D401
            pass

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                return self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/boxes":
                return self._send(wf.read_bytes(), "application/json; charset=utf-8")
            for pre in ("/img/", "/preview/"):
                if path.startswith(pre):
                    name = Path(unquote(path[len(pre):])).name           # 폴더 밖 파일은 못 읽게 이름만
                    p = src / name
                    if not p.exists():
                        return self._send(b"", "text/plain", 404)
                    img = _read(p)
                    if pre == "/preview/":
                        d = json.loads(wf.read_text(encoding="utf-8")).get(name) or {}
                        img = mosaic(img, d.get("boxes", []))
                    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    return self._send(buf.tobytes(), "image/jpeg")
            self._send(b"", "text/plain", 404)

        def do_POST(self):
            if urlparse(self.path).path != "/save":
                return self._send(b"", "text/plain", 404)
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            json.loads(body)                                              # 형식 확인
            wf.write_bytes(body)
            self._send(b"ok", "text/plain")

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)                    # 내 PC에서만 열림
    print(f"확인 페이지: http://127.0.0.1:{port}  (끝내려면 Ctrl+C)")
    srv.serve_forever()


def apply(src: Path, push: bool = False) -> None:
    import subprocess

    from PIL import Image
    import cv2
    data = json.loads((work_dir(src) / "boxes.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.jpg"):
        f.unlink()                                                          # 이전 결과는 지우고 다시 만든다
    items, per_day = [], {}
    for p in photos(src):
        d = data.get(p.name)
        if not d or d.get("skip"):
            continue
        day = d["date"] or "0000-00-00"
        per_day[day] = per_day.get(day, 0) + 1
        name = f"{day}_{per_day[day]}.jpg"
        img = finish(Image.fromarray(cv2.cvtColor(mosaic(_read(p), d["boxes"]), cv2.COLOR_BGR2RGB)), d)
        big = img.copy()
        big.thumbnail((SIZE, SIZE), Image.LANCZOS)
        big.save(OUT / name, "JPEG", quality=82, optimize=True, progressive=True)        # exif 없이 저장
        th = img.copy()
        th.thumbnail((640, 640), Image.LANCZOS)
        th.save(OUT / f"t_{name}", "JPEG", quality=78, optimize=True, progressive=True)
        items.append({"date": day, "src": f"study/growth/{name}", "thumb": f"study/growth/t_{name}"})
    DATA.write_text(json.dumps({"id": "growth", "title": TITLE, "intro": INTRO, "photos": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"사진 {len(items)}장 → {OUT}")
    if push:
        run = lambda *a: subprocess.run(["git", *a], cwd=ROOT, check=True)
        run("add", "study/growth", "data/growth.json")
        run("commit", "-q", "-m", f"가치 투자 성장 스토리 사진 {len(items)}장(운영자 외 얼굴 모자이크)")
        run("pull", "-q", "--rebase", "--autostash")
        run("push", "-q")
        print("push 완료")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3 or sys.argv[1] not in ("detect", "review", "apply"):
        print(__doc__)
        sys.exit(1)
    s = Path(sys.argv[2])
    {"detect": lambda: detect(s), "review": lambda: review(s), "apply": lambda: apply(s, "--push" in sys.argv)}[sys.argv[1]]()
