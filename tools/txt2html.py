"""블로그 txt → 색깔 박스 html (인라인 스타일만). 사용: python txt2html.py <txt> <html> <탭제목>"""
import html
import re
import sys

src, dst, tab = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(src, encoding="utf-8").read()
body, cta = text.split("━━━━━━━━━━━━━━━", 1)
lines = body.strip("\n").splitlines()

COLORS = ["#0b3a4a", "#9b1c1c", "#123f8c", "#1e6b3a", "#7a4bc2", "#b25e09", "#0f7f8c", "#8a2b6d", "#4b5563", "#9b1c1c", "#123f8c", "#4b2a85"]
LIGHT = {"#0b3a4a": "#eef6f8", "#9b1c1c": "#fff5f4", "#123f8c": "#f5f8ff", "#1e6b3a": "#f4faf6", "#7a4bc2": "#f7f3fd",
         "#b25e09": "#fff8ef", "#0f7f8c": "#eef9fa", "#8a2b6d": "#fdf3f9", "#4b5563": "#f6f7f9", "#4b2a85": "#f7f3fd"}


def esc(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"(\d[\d,.]*\s?(?:%|bp|달러|억 달러|조 원|GW|배))", r"<b>\1</b>", s)
    return s


out = []
title = lines[0]
tags = lines[2]
i = 3
sec = -1
open_box = False
in_list = False


def close_list():
    global in_list
    if in_list:
        out.append("</ul>")
        in_list = False


def close_box():
    global open_box
    close_list()
    if open_box:
        out.append("</div>")
        open_box = False


summary_mode = False
for ln in lines[3:]:
    s = ln.strip()
    if not s:
        continue
    if s.startswith("📌 한 줄 요약"):
        summary_mode = True
        out.append('<div style="background:#0b3a4a;color:#fff;border-radius:12px;padding:18px 20px;margin:0 0 20px;">'
                   '<p style="margin:0 0 6px;font-weight:bold;color:#ffd166;font-size:17px;">📌 한 줄 요약</p>')
        continue
    if summary_mode:
        if s.startswith("("):
            out.append("</div>")
            out.append(f'<p style="margin:0 0 24px;font-size:14px;color:#666;">{esc(s)}</p>')
            summary_mode = False
        else:
            out.append(f'<p style="margin:0;">{esc(s)}</p>')
        continue
    m = re.match(r"^(\S+)\s+(\d+)\.\s+(.*)$", s)
    if m:  # 큰 섹션
        close_box()
        sec += 1
        c = COLORS[sec % len(COLORS)]
        out.append(f'<h2 style="font-size:21px;border-left:6px solid {c};padding-left:10px;margin:36px 0 12px;color:{c};">{esc(s)}</h2>')
        out.append(f'<div style="border:1px solid #e3e7ee;border-radius:12px;padding:14px 18px;margin:0 0 10px;background:{LIGHT[c]};">')
        open_box = True
        continue
    if s.startswith("💡 정리") and len(s) < 10:
        close_box()
        out.append('<div style="background:#0b3a4a;color:#fff;border-radius:12px;padding:18px 20px;margin:30px 0 20px;">'
                   '<p style="margin:0 0 6px;font-weight:bold;color:#ffd166;font-size:17px;">💡 정리</p>')
        summary_mode = "end"
        continue
    if s.startswith("자료:"):
        close_box()
        out.append(f'<p style="font-size:13px;color:#888;margin:0 0 6px;">{esc(s)}</p>')
        continue
    if s.startswith("- "):
        if not in_list:
            out.append('<ul style="margin:4px 0 10px;padding-left:20px;">')
            in_list = True
        out.append(f'<li style="margin:0 0 6px;">{esc(s[2:])}</li>')
        continue
    close_list()
    if s.startswith("→") or s.startswith("💡 정리:"):
        out.append(f'<p style="margin:8px 0 10px;padding:10px 14px;background:#fff3e0;border-radius:8px;">{esc(s)}</p>')
    elif re.match(r"^[^\w\s(\-→]", s) and len(s) < 60:  # 작은 소제목(이모지로 시작)
        out.append(f'<p style="margin:12px 0 6px;font-weight:bold;">{esc(s)}</p>')
    else:
        out.append(f'<p style="margin:0 0 10px;">{esc(s)}</p>')

# '정리' 박스가 열린 상태로 끝났다면 처리: 정리 본문은 자료 줄 앞에서 닫혀야 함
res = "\n".join(out)
res = res.replace('<p style="font-size:13px;color:#888;margin:0 0 6px;">자료:',
                  '</div>\n<p style="font-size:13px;color:#888;margin:0 0 6px;">자료:', 1) if summary_mode == "end" else res
res = res.replace("<p style=\"margin:0;\">", "<p style=\"margin:0;\">")

CTA = open(sys.argv[4], encoding="utf-8").read() if len(sys.argv) > 4 else ""
page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(tab)}</title>
</head>
<body style="margin:0;background:#ffffff;">
<!-- 블로그 붙여넣기: 브라우저에서 이 파일을 열고 Ctrl+A → Ctrl+C → 블로그 편집기에 Ctrl+V -->
<div style="max-width:760px;margin:0 auto;padding:24px 16px;font-family:'Noto Sans KR','Malgun Gothic',sans-serif;color:#222;line-height:1.75;font-size:16px;">

<h1 style="font-size:26px;line-height:1.4;margin:0 0 14px;color:#0b3a4a;">{html.escape(title)}</h1>
<p style="margin:0 0 26px;color:#0f7f8c;font-size:15px;">{html.escape(tags)}</p>

{res}

{CTA}

<p style="font-size:13px;color:#888;">※ 본 글은 투자 참고용이며, 투자 판단의 최종 책임은 본인에게 있습니다.</p>
</div>
</body>
</html>
"""
open(dst, "w", encoding="utf-8").write(page)
print("ok", len(page))
