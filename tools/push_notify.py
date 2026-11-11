"""📲 TRL 앱 푸시 알림 보내기(웹 푸시, 무료) — 2026-11-12 운영자 요청.

휴대폰 TRL 앱(홈 화면에 설치한 사이트)에서 '🔔 알림 받기' → 화면에 나온 코드(TRLPUSH:…)를 이 PC에 등록:
  python tools/push_notify.py add "TRLPUSH:...."      # 기기 등록(코드는 그대로 붙여 넣기)
  python tools/push_notify.py list                    # 등록된 기기(주소 끝부분만)
  python tools/push_notify.py test                    # 시험 알림 1건
  python tools/push_notify.py remove 2                # 2번 기기 지우기

다른 코드에서:  from push_notify import push; push("제목", "본문", "https://.../#brief")   # 실패해도 예외 없음
- 보내는 키(개인 키)는 이 PC의 ~/.tg_notify/vapid_private.pem (저장소에 넣지 않음, 키 묶음으로만 옮김).
  공개 키는 pwa.js 의 VAPID_PUBLIC 과 짝이다 — 개인 키를 바꾸면 pwa.js 공개 키도 바꾸고 기기를 다시 등록해야 한다.
- 등록 기기: ~/.tg_notify/push_subs.json (실행 PC가 바뀌어도 쓰이도록 market-site failover 상태 공유에 포함).
- 기기가 알림을 끄거나 앱을 지우면(410/404) 그 기기는 자동으로 지운다.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

HOME = Path.home() / ".tg_notify"
KEY = HOME / "vapid_private.pem"
SUBS = HOME / "push_subs.json"
SITE = "https://ingforme82-commits.github.io/trend-lab/"
CLAIM = {"sub": "https://ingforme82-commits.github.io/trend-lab/"}   # 연락처 칸(이메일 대신 사이트 주소)


def _subs() -> list[dict]:
    try:
        return json.loads(SUBS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _save(s: list[dict]) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    SUBS.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def push(title: str, body: str, url: str = SITE, tag: str = "") -> int:
    """등록된 모든 기기에 알림. 보낸 기기 수. 키·기기가 없거나 실패해도 예외 없음."""
    try:
        from pywebpush import WebPushException, webpush
    except Exception:  # noqa: BLE001
        return 0
    subs = _subs()
    if not subs or not KEY.exists():
        return 0
    data = json.dumps({"title": title[:80], "body": body[:600], "url": url, "tag": tag}, ensure_ascii=False)
    ok, keep = 0, []
    for s in subs:
        try:
            webpush(subscription_info=s["sub"], data=data, vapid_private_key=str(KEY), vapid_claims=dict(CLAIM), ttl=3600)
            ok += 1
            keep.append(s)
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", 0)
            if code not in (404, 410):                       # 지워진 기기만 버림, 일시 오류는 남김
                keep.append(s)
        except Exception:  # noqa: BLE001
            keep.append(s)
    if len(keep) != len(subs):
        _save(keep)
    return ok


def main() -> None:
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    cmd = a[0] if a else "list"
    subs = _subs()
    if cmd == "add" and len(a) > 1:
        code = a[1].strip().removeprefix("TRLPUSH:")
        sub = json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)).decode("utf-8"))
        if not sub.get("endpoint") or not (sub.get("keys") or {}).get("p256dh"):
            raise SystemExit("코드가 올바르지 않습니다(TRLPUSH: 로 시작하는 전체를 붙여 넣으세요)")
        subs = [s for s in subs if s["sub"]["endpoint"] != sub["endpoint"]] + [{"sub": sub, "name": a[2] if len(a) > 2 else f"기기{len(subs) + 1}"}]
        _save(subs)
        print(f"등록 완료 — 기기 {len(subs)}대. 시험: python tools/push_notify.py test")
    elif cmd == "remove" and len(a) > 1:
        i = int(a[1]) - 1
        print(f"지움: {subs.pop(i)['name']}") if 0 <= i < len(subs) else print("번호 없음")
        _save(subs)
    elif cmd == "test":
        print(f"보냄 {push('✅ TRL 앱 알림 연결', '실적 공시·06:10 브리핑·PC 전환 알림이 이 앱으로도 옵니다.', SITE, 'test')}대 / 등록 {len(subs)}대"
              + ("" if KEY.exists() else " — 보내는 키 없음(~/.tg_notify/vapid_private.pem)"))
    else:
        print(f"등록 기기 {len(subs)}대 · 보내는 키 {'있음' if KEY.exists() else '없음'}")
        for i, s in enumerate(subs, 1):
            print(f"  {i}. {s['name']} …{s['sub']['endpoint'][-16:]}")


if __name__ == "__main__":
    main()
