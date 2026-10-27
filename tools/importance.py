"""📊 속보 중요도(0~100) — 모든 텔레그램·RSS·자동 집계 글에 매긴다. 규칙 기반(AI 문장 생성 없음).

가점: 변곡점 직전·동안 뉴스(pivot) · 속보성 키워드(hot) · 주요 인물·기관 발언 · 공식 발표·복수 출처·외신 확인 · 오늘 시장 주제 분야
      · '상승/하락 이유·원인·배경'을 설명하는 글 · 지수·유가 % 움직임 언급 · 시황 분석 채널(카이에 드 마켓·나쁜양파 등)
감점: 분류 '기타'(시장 키워드 없음) · 아주 짧은 글
등급: 상(60↑) · 중(35~59) · 하
"""

from __future__ import annotations

import re

KEY = re.compile(r"트럼프|Trump|파월|Powell|연준|FOMC|OPEC|오펙|사우디|이란|하메네이|네타냐후|푸틴|시진핑|백악관|재무장관|베선트|"
                 r"한은|한국은행|이창용|기재부|금융위|BOJ|일본은행|ECB|라가르드")
EXPLAIN = re.compile(r"(?:상승|하락|급등|급락|반등|약세|강세)\s?(?:의\s?)?(?:이유|원인|배경|요인)|이유는|원인은|때문에|덕분에|영향으로|"
                     r"왜\s?(?:올랐|빠졌|오르|내리)|(?:오른|빠진|오르는|내리는)\s?이유|배경에는|주도한|견인|끌어올|끌어내|"
                     r"(?:상승|급등|하락|급락)\s?출발|수혜|모멘텀")
THEME = {"반도체", "AI·빅테크", "중동·유가", "연준·금리", "지수"}
MOVE = re.compile(r"(니케이|닛케이|코스피|코스닥|나스닥|S&P|다우|항셍|선물|유가|WTI|브렌트|금값|국채|환율|원/달러|SOX|반도체 지수)"
                  r".{0,25}\d+(?:\.\d+)?\s?%")
KIND_BONUS = {"시황 분석": 25, "증권사 시황": 12, "섹터 시세": 8, "관전 포인트": 10}   # 시황 분석 = 운영자가 골라 둔 분석 채널(카이에 드 마켓·나쁜양파·가치투자클럽)


def score(it: dict) -> int:
    t = f"{it.get('text', '')} {it.get('sub', '')}"
    s = 15
    s += 8 if THEME & set(it.get("tags") or []) else 0
    s += 35 if it.get("pivot") else 0
    s += 15 if it.get("hot") else 0
    s += 12 if KEY.search(t) else 0
    s += {"official": 15, "multi": 12}.get(it.get("verify", ""), 0)
    s += 8 if (it.get("xc") or {}).get("st") == "ok" else 0
    s += min(10, 3 * max(0, (it.get("nsrc") or 1) - 1))
    s += 15 if EXPLAIN.search(t) else 0
    s += 10 if MOVE.search(t) else 0
    s += KIND_BONUS.get(it.get("kind", ""), 0)
    s -= 10 if (it.get("tags") or []) == ["기타"] else 0
    s -= 5 if len(it.get("text", "")) < 20 else 0
    return max(0, min(100, s))


def level(s: int) -> str:
    return "상" if s >= 60 else "중" if s >= 35 else "하"


def apply(items: list[dict]) -> None:
    for it in items:
        it["imp"] = score(it)
        it["lv"] = level(it["imp"])
