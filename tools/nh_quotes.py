"""NH 공식 현재가 → KORU·SOXL 공개 시세. 인증정보·계좌정보는 저장/출력하지 않는다."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.nhplug.com:8443"
REPO = "ingforme82-commits/trend-lab"
SESSIONS = {"0": "pre", "1": "reg", "2": "post", "3": "day"}
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
STATUS = Path.home() / ".cache" / "trl-nh-quotes-status.json"


def write_status(ok, error=None):
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({"checked_at": int(time.time() * 1000), "ok": ok, "error": error}), encoding="utf-8")


def request(path, payload, token=None):
    headers = {"Content-Type": "application/json; charset=UTF-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
        body = json.dumps(payload).encode()
    else:
        path += "?" + urllib.parse.urlencode(payload)
        body = b""
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    with urllib.request.urlopen(urllib.request.Request(BASE + path, data=body, headers=headers), timeout=20) as response:
        return json.load(response)


def credentials(path):
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"\s*(?:(?:NH|NHPLUG)[_ ])?(app[_\s]*key|app[_\s]*secret(?:[_\s]*key)?)\s*[:=]\s*(.*?)\s*$", line, re.I)
        if match:
            key = "secret" if "secret" in match[1].lower() else "key"
            values[key] = match[2].strip("\"'")
    if not values.get("key") or not values.get("secret"):
        raise ValueError("NH credential format")
    return values


def access_token(path):
    # 사용자 전용 로컬 캐시: 공개 저장소 밖에 둔다.
    cache = Path.home() / ".cache" / "trl-nh-quotes-token.json"
    try:
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved["expires"] > time.time() + 120:
            return saved["token"]
    except (OSError, ValueError, KeyError):
        pass
    keys = credentials(path)
    data = request("/oauth2/token", {"appkey": keys["key"], "appsecretkey": keys["secret"], "grant_type": "client_credentials", "scope": "oob"})
    token = data["access_token"]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"token": token, "expires": time.time() + int(data["expires_in"])}), encoding="utf-8")
    return token


def normalize(row, checked_at):
    sess = SESSIONS.get(str(row.get("marketperiod_cls")))
    px, base = float(row["trdprc"]), float(row["normal_trdprc"])
    if not sess or px <= 0 or base <= 0:
        raise ValueError("NH quote unavailable")
    return {"sess": sess, "px": px, "base": base, "change": round(px - base, 4), "chg": round((px / base - 1) * 100, 2),
            "checked_at": checked_at, "source": "NH투자증권", "source_date": row.get("trade_date"), "source_time": row.get("quote_time"),
            "live": sess != "reg", "stale": sess == "reg"}


def gh(args, payload=None):
    if payload is None:
        result = subprocess.run(["gh", "api", *args], capture_output=True, text=True, encoding="utf-8", timeout=35, creationflags=NO_WINDOW)
    else:
        with tempfile.TemporaryDirectory(prefix="trl-nh-") as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(["gh", "api", *args, "--input", str(path)], capture_output=True, text=True, encoding="utf-8", timeout=35, creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError("GitHub quote publish failed")
    return json.loads(result.stdout)


def publish(data):
    endpoint = f"repos/{REPO}/contents/nh-quotes.json"
    try:
        current = gh([endpoint + "?ref=quotes"])
    except RuntimeError:
        current = {}
    payload = {"branch": "quotes", "message": "NH KORU·SOXL 현재 시세 자동 갱신", "content": base64.b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()}
    if current.get("sha"):
        payload["sha"] = current["sha"]
    gh(["--method", "PUT", endpoint], payload)


def main():
    parser = argparse.ArgumentParser()
    # 키 파일 위치: 환경변수 → 바탕화면 NH.txt → ~/.nhplug/.env (11/8 바탕화면 파일이 없어 멈췄던 문제)
    keyfile = next((p for p in (os.environ.get("NH_APP_KEY_FILE"), r"D:\Desktop\NH.txt", str(Path.home() / ".nhplug" / ".env")) if p and Path(p).is_file()),
                   str(Path.home() / ".nhplug" / ".env"))
    parser.add_argument("--credentials", type=Path, default=Path(keyfile))
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    token = access_token(args.credentials)
    rows = []
    for sym in ("KORU", "SOXL"):
        response = request("/gbstock/quote/v1/current", {"Input_0": {"iem_cd": sym}}, token)
        if response.get("rsp_cd") != "00000":
            raise ValueError("NH quote rejected")
        rows.append({"sym": sym, **normalize(response["Output_0"], int(time.time() * 1000))})
    data = {"updated": int(time.time() * 1000), "source": "NH투자증권", "items": rows}
    if args.publish:
        publish(data)
    write_status(True)
    if not args.quiet and sys.stdout is not None:
        print(json.dumps(data, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # 공급자 응답·키·토큰·요청 URL은 로그에 쓰지 않는다.
        write_status(False, type(error).__name__)
        if "--quiet" not in sys.argv and sys.stdout is not None:
            print("NH quote update failed:", type(error).__name__)
        raise SystemExit(1) from None
