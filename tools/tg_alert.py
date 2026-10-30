"""🔔 텔레그램 이슈 알림 — 운영자 개인 대화방으로 '이슈'만(카톡 대신, 2026-10-30 운영자 결정). 공개 채널 아님.

설정(저장소 밖, 공유·업로드 금지):  %USERPROFILE%\\.tg_notify\\.env
  TG_BOT_TOKEN=…        # @BotFather /newbot 으로 받은 토큰(기존 tg_notify 와 같은 봇 써도 됨)
  TG_ALERT_CHAT=…       # 운영자 개인 chat id — 'python tools/tg_alert.py find-chat' 으로 찾음
  TG_ALERT_ON=1         # 1 일 때만 실제 전송. 없거나 0 이면 tools/alert_outbox.log 에만 기록(미리 보기)

  python tools/tg_alert.py setup        # .env 양식에 알림 항목 추가(값은 메모장으로 직접)
  python tools/tg_alert.py find-chat    # 봇에게 먼저 /start 를 보낸 뒤 실행 → chat id 만 표시(토큰은 표시 안 함)
  python tools/tg_alert.py status       # 켜짐/꺼짐·설정 유무
  python tools/tg_alert.py test         # 시험 알림 1건(켜져 있을 때만 전송)

다른 코드에서:  from tg_alert import alert; alert("변곡점", "WTI-123", "🔴 WTI +1.2% …")   # 실패해도 예외 없음
- 같은 (종류, 키)는 30분 안에 다시 보내지 않는다. 한 번에 3,900자까지.
- 보내는 것: 변곡점 · 운영자 가격대 도달·이탈 · 주도 섹터 1위 교체 · 모의매매 주문 결과 — 사실·수치만, 키·토큰·계좌번호 없음.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HOME = Path.home() / ".tg_notify"
ENV = HOME / ".env"
STATE = HOME / "alert_state.json"
OUTBOX = Path(__file__).resolve().parent / "alert_outbox.log"
DEDUP_S = 30 * 60
TEMPLATE_ADD = "\n# ── 이슈 알림(운영자 개인 대화방) ──\nTG_ALERT_CHAT=여기에_chat_id\nTG_ALERT_ON=0\n"


def _env() -> dict[str, str]:
    out = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def _ready(e: dict) -> bool:
    return bool(e.get("TG_BOT_TOKEN")) and "여기에" not in e.get("TG_BOT_TOKEN", "") and e.get("TG_ALERT_CHAT", "").lstrip("-").isdigit()


def _call(token: str, method: str, **data) -> dict:
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=urllib.parse.urlencode(data).encode())
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def _seen(kind: str, key: str) -> bool:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    now = time.time()
    k = f"{kind}|{key}"
    if now - st.get(k, 0) < DEDUP_S:
        return True
    st = {a: b for a, b in st.items() if now - b < 86400}
    st[k] = now
    try:
        HOME.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(st), encoding="utf-8")
    except OSError:
        pass
    return False


def alert(kind: str, key: str, text: str) -> bool:
    """이슈 알림 1건. 켜져 있으면 텔레그램 전송, 아니면 alert_outbox.log 에만. 실패해도 예외 없음. 보냈으면 True."""
    try:
        if _seen(kind, key):
            return False
        msg = f"🔔 [{kind}] {datetime.now():%m/%d %H:%M}\n{text}"[:3900]
        e = _env()
        if e.get("TG_ALERT_ON") == "1" and _ready(e):
            r = _call(e["TG_BOT_TOKEN"], "sendMessage", chat_id=e["TG_ALERT_CHAT"], text=msg, disable_web_page_preview="true")
            if r.get("ok"):
                return True
        with OUTBOX.open("a", encoding="utf-8") as f:                 # 꺼져 있거나 실패: 미리 보기 기록
            f.write(msg.replace("\n", " ⏎ ") + "\n")
    except Exception:  # noqa: BLE001
        pass
    return False


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    e = _env()
    if cmd == "setup":
        HOME.mkdir(exist_ok=True)
        cur = ENV.read_text(encoding="utf-8") if ENV.exists() else "# 텔레그램 @BotFather 토큰(공유·업로드 금지)\nTG_BOT_TOKEN=여기에_봇_토큰\n"
        if "TG_ALERT_CHAT" not in cur:
            ENV.write_text(cur.rstrip("\n") + "\n" + TEMPLATE_ADD, encoding="utf-8")
        print(f"설정 파일: {ENV} — 메모장으로 열어 TG_BOT_TOKEN 을 넣고, 봇에게 /start 를 보낸 뒤 'find-chat'")
    elif cmd == "find-chat":
        if not e.get("TG_BOT_TOKEN") or "여기에" in e["TG_BOT_TOKEN"]:
            sys.exit(f"{ENV} 에 TG_BOT_TOKEN 이 없습니다")
        ups = _call(e["TG_BOT_TOKEN"], "getUpdates").get("result", [])
        chats = {}
        for u in ups:
            c = (u.get("message") or u.get("my_chat_member") or {}).get("chat") or {}
            if c.get("type") == "private":
                chats[c["id"]] = c.get("first_name", "")
        print("개인 대화방 chat id:", ", ".join(f"{k}({v})" for k, v in chats.items()) or "없음 — 봇에게 먼저 /start 를 보내세요")
        print(f"→ {ENV} 의 TG_ALERT_CHAT 에 넣고, TG_ALERT_ON=1 로 바꾸면 켜집니다")
    elif cmd == "test":
        print("보냄" if alert("시험", str(time.time()), "트렌드랩 이슈 알림 시험입니다.") else f"보내지 않음(꺼짐·미설정) → {OUTBOX} 기록")
    else:
        print(f"이슈 알림: {'켜짐' if e.get('TG_ALERT_ON') == '1' and _ready(e) else '꺼짐(기록만)'} · 봇 토큰 {'있음' if e.get('TG_BOT_TOKEN') and '여기에' not in e.get('TG_BOT_TOKEN', '') else '없음'}"
              f" · chat id {'있음' if e.get('TG_ALERT_CHAT', '').lstrip('-').isdigit() else '없음'} (값은 표시하지 않음) · 미리 보기 {OUTBOX}")


if __name__ == "__main__":
    main()
