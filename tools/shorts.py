"""🎬 저항선 매매 판단 숏츠 시제품(운영자 11/20) — 추세 판단(chan.py) 결과로 세로 영상 1편을 만든다.

  python tools/shorts.py 000660            # SK하이닉스 편 → 바탕화면 trlab_shorts/
  python tools/shorts.py 000660 --json f   # chan 대신 저장해 둔 종목 JSON으로(확인용)
  python tools/shorts.py --daily kr        # 매일 자동(11/20 운영자): 한국 장 마감 뒤 많이 움직인 종목 2~3개 → 바탕화면 trlab_shorts/날짜/
  python tools/shorts.py --daily us        # 미국 장 마감 뒤(한국 아침). 예약 작업 등록: scripts/register-shorts.ps1

- 장면: ① 오늘 등락 ② 아래 지지(스윙 저점) ③ 위 저항(5일선) ④ 돌파 기준(채널 상단 +1%) ⑤ 정리·trlab.net
- 문장은 숫자에서 만든다(고가가 5일선에 닿았는지, 저가가 지지선 1% 안에서 멈췄는지 등 실제 값으로 판단).
- 음성 = edge-tts(무료), 영상 = imageio-ffmpeg 내장 ffmpeg. 업로드는 하지 않는다(확인 후 직접 올리기).
사실과 숫자만 말한다. 매수·매도 권유가 아니다.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import edge_tts
import imageio_ffmpeg
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

FONT = Path("C:/Windows/Fonts/malgunbd.ttf")
font_manager.fontManager.addfont(str(FONT))
plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(FONT)).get_name()
plt.rcParams["axes.unicode_minus"] = False

OUT = Path.home() / "Desktop" / "trlab_shorts"
VOICE = "ko-KR-SunHiNeural"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
BG, PANEL, INK, DIM = "#0f1b2d", "#14263b", "#ffffff", "#8fa3ba"
UP, DN = "#ff4d5e", "#4d8dff"                   # 한국식: 상승 빨강·하락 파랑
C_CH, C_LO, C_MA, C_SUP = "#f6c773", "#60738a", "#ffe14d", "#3ddc97"
BARS = 30


KR = True                                            # 지금 만드는 종목이 원화(한국)인지 — build()가 정한다


def won(v: float) -> str:
    """읽기용 가격. 원화 1137000 → '113만 7천 원'(천 원 단위), 달러 145.98 → '145.98달러'."""
    if not KR:
        return f"{v:,.2f}달러"
    v = int(round(v / 1000)) * 1000
    man, chun = divmod(v // 1000, 10)
    if not man:
        return f"{v:,}원"
    return f"{man:,}만{f' {chun}천' if chun else ''} 원".replace(",", "")


def ga(word: str) -> str:
    """'…원' 뒤 '이', '…달러' 뒤 '가'."""
    return word + ("이" if word.endswith("원") else "가")


def num(v: float) -> str:
    return f"{v:,.0f}" if KR else f"${v:,.2f}"


def script(it: dict) -> list[dict]:
    rows = it["rows"]
    d, o, h, l, c = rows[-1]
    ma5, sup, sup_day = it["ma5"], it.get("sup_h"), it.get("sup_day")
    bo = max(it["up_next"] * 1.01, ma5)                  # 돌파 확인 = 채널 상단 +1%와 5일선을 둘 다 넘는 종가 → 둘 중 높은 값
    ma_high = ma5 > it["up_next"] * 1.01
    name, chg = it["name"], it["chg"]
    word = ("급등" if chg >= 3 else "상승") if chg >= 0 else ("급락" if chg <= -3 else "하락")
    q = "지금 사도 될까?" if chg < 0 or c < ma5 else "더 갈 수 있을까?"
    sc = [{"focus": "hook", "say": f"{name} {'오늘' if KR else '간밤'} {abs(chg):.1f}% {word}. {q} 선 세 개만 보세요.",
           "cap": f"{name} {chg:+.2f}%\n{q}"}]
    if sup:
        held = l >= sup and (l / sup - 1) <= 0.01
        sm, sd = int(sup_day.split("/")[0]), int(sup_day.split("/")[1])
        sc.append({"focus": "sup",
                   "say": f"먼저 아래 지지선. {sm}월 {sd}일 저점, {won(sup)}입니다. " +
                          (f"오늘 저가 {won(l)}, 이 선 바로 위에서 멈췄습니다." if held else
                           f"오늘 저가는 {won(l)}입니다." if l >= sup else f"오늘 저가 {won(l)}, 이 선을 깼습니다."),
                   "cap": f"▼ 지지 {num(sup)}\n오늘 저가 {num(l)}"})
    if c < ma5:
        sc.append({"focus": "ma",
                   "say": f"위 저항은 5일선, {won(ma5)}입니다. " +
                          (f"고가는 {won(h)}, 5일선에 닿지도 못했습니다." if h < ma5 else f"고가 {won(h)}에서 5일선을 건드리고 밀렸습니다."),
                   "cap": f"▲ 저항 5일선 {num(ma5)}\n고가 {num(h)}"})
    else:
        sc.append({"focus": "ma", "say": f"종가가 5일선 {won(ma5)} 위에서 끝났습니다. 이제 5일선이 아래 지지선입니다.",
                   "cap": f"5일선 {num(ma5)} 위 마감\n종가 {num(c)}"})
    done = it.get("state") == "돌파 확인"
    sc.append({"focus": "ch",
               "say": ("하락 채널 상단을 1% 넘게 뚫고 마감했습니다. 돌파 확인입니다. 다음은 이 자리를 지키는지 봅니다." if done else
                       (f"돌파 기준은 하락 채널 상단입니다. 다음 거래일 상단 {won(it['up_next'])}, 1%를 더해도 5일선이 더 높아서, 5일선 {won(bo)} 위에서 종가가 끝나야 돌파 확인입니다." if ma_high else
                        f"돌파 기준은 하락 채널 상단입니다. 다음 거래일 상단 {won(it['up_next'])}, 여기에 1%를 더한 {won(bo)} 위에서 종가가 끝나야 돌파 확인입니다.")),
               "cap": "돌파 확인\n(채널 상단 +1% · 5일선 위)" if done else f"돌파 확인 = 종가 {num(bo)} 위\n(채널 상단 +1% · 5일선 위)"})
    if done:
        say = f"정리합니다. 돌파 확인 상태입니다. 종가가 5일선 {won(ma5)} 아래로 내려가면 다시 경계합니다."
        cap = f"돌파 확인 유지 중\n이탈 기준 = 5일선 {num(ma5)}"
    elif c >= ma5:
        say = f"정리합니다. 5일선 회복은 했고, 남은 건 채널 상단 {won(bo)} 돌파입니다. 그 전까지는 확인이 더 필요합니다."
        cap = f"① 5일선 회복 ✓\n② 종가 > {num(bo)} 대기"
    else:
        say = "정리합니다. 첫째, 종가 5일선 회복. 둘째, 채널 상단 돌파. 둘 다 아니면 기다립니다." + (f" {ga(won(sup))} 깨지면 지지 이탈입니다." if sup else "")
        cap = f"① 종가 > 5일선 {num(ma5)}\n② 종가 > {num(bo)}\n둘 다 아니면 관망"
    sc.append({"focus": "end", "say": say + " 매일 판단은 티알랩 닷 넷에서 확인하세요.", "cap": cap, "end": True})
    return sc


def frame(it: dict, s: dict, path: Path) -> None:
    rows = it["rows"][-BARS:]
    off = len(it["rows"]) - len(rows)
    n = len(rows)
    closes = [r[4] for r in it["rows"]]
    ma = [sum(closes[i - 4:i + 1]) / 5 if i >= 4 else None for i in range(len(closes))][-BARS:]
    f = s["focus"]
    a = lambda key: 1.0 if f in (key, "end") else 0.25          # 지금 말하는 선만 진하게

    fig = plt.figure(figsize=(10.8, 19.2), dpi=100, facecolor=BG)
    # 위 제목
    fig.text(0.06, 0.945, it["name"], color=INK, fontsize=64, va="top")
    fig.text(0.06, 0.885, f"{num(it['px'])}  {it['chg']:+.2f}%", color=UP if it["chg"] >= 0 else DN, fontsize=44, va="top")
    fig.text(0.94, 0.94, f"{it['day']} · 추세 판단", color=DIM, fontsize=26, va="top", ha="right")

    ax = fig.add_axes([0.05, 0.36, 0.64, 0.47], facecolor=PANEL)
    for sp in ax.spines.values():
        sp.set_visible(False)
    for i, (_, o, h, l, c) in enumerate(rows):
        col = UP if c >= o else DN
        ax.plot([i, i], [l, h], color=col, lw=2.2, zorder=2)
        ax.add_patch(Rectangle((i - 0.33, min(o, c)), 0.66, max(abs(c - o), h * 0.0008), color=col, zorder=3))
    # 5일선
    xs = [i for i in range(n) if ma[i]]
    ax.plot(xs, [ma[i] for i in xs], color=C_MA, lw=5 if f in ("ma", "end") else 3, alpha=a("ma"), zorder=4)
    # 채널 상단·하단(마지막 봉 기준 값 + 기울기, 다음 봉까지)
    last = len(it["rows"]) - 1
    for start, now, slope, col, key in ((it["upper_start"], it["up_now"], it["su"], C_CH, "ch"), (it["lower_start"], it["lo_now"], it["sl"], C_LO, "sup")):
        x0 = max(start, off)
        xx = [x0 - off, n]
        yy = [now + slope * (x0 - last), now + slope * (last + 1 - last)]
        ax.plot(xx, yy, color=col, lw=5 if f in (key, "end") and key == "ch" else 3, alpha=a(key) if key == "ch" else 0.5, ls="-" if key == "ch" else "--", zorder=4)
    if f in ("ch", "end"):
        bo = max(it["up_next"] * 1.01, it["ma5"])
        ax.plot([n - 3, n + 1.4], [bo, bo], color=UP, lw=4, ls=":", zorder=5)
        ax.text(n + 1.5, bo, f"돌파 {num(bo)}", color=UP, fontsize=24, va="center")
    if it.get("sup_h"):
        ax.axhline(it["sup_h"], color=C_SUP, lw=4 if f in ("sup", "end") else 2, alpha=a("sup"), zorder=4)
        ax.text(n + 1.5, it["sup_h"], f"지지 {num(it['sup_h'])}", color=C_SUP, fontsize=24, va="center", alpha=a("sup"))
    ax.text(n + 1.5, it["ma5"], f"5일선 {num(it['ma5'])}", color=C_MA, fontsize=24, va="center", alpha=a("ma"))
    lo = min(r[3] for r in rows); hi = max(r[2] for r in rows)
    ax.annotate("오늘", (n - 1, rows[-1][3]), xytext=(n - 1, rows[-1][3] - (hi - lo) * 0.05), color=INK, fontsize=22, ha="center", va="top",
                arrowprops={"arrowstyle": "-", "color": INK, "lw": 2})
    ax.set_ylim(lo - (hi - lo) * 0.12, hi + (hi - lo) * 0.06)
    ax.set_xlim(-1, n + 1)
    ax.set_xticks([0, n // 2, n - 1], [rows[0][0], rows[n // 2][0], rows[-1][0]])
    ax.tick_params(colors=DIM, labelsize=22, length=0)
    ax.yaxis.tick_right(); ax.set_yticks([])
    ax.grid(axis="y", color="#20354d", lw=1)

    # 아래 자막 상자
    fig.patches.append(FancyBboxPatch((0.05, 0.10), 0.90, 0.21, boxstyle="round,pad=0.01,rounding_size=0.02",
                                      transform=fig.transFigure, fc="#1d3350", ec=C_CH if s.get("end") else "#2c4767", lw=3))
    fig.text(0.5, 0.205, s["cap"], color=INK, fontsize=50 if s["focus"] == "hook" else 42, ha="center", va="center", linespacing=1.45)
    fig.text(0.5, 0.06, "trlab.net", color=C_CH, fontsize=40, ha="center", va="center")
    fig.text(0.5, 0.025, "사실·숫자 정리이며 매수·매도 권유가 아닙니다", color=DIM, fontsize=22, ha="center", va="center")
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def run(cmd: list) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def speak(text: str, path: Path) -> None:
    await edge_tts.Communicate(text, VOICE, rate="+20%").save(str(path))


def build(it: dict, out: Path = OUT) -> Path:
    global KR
    KR = str(it["code"]).isdigit()
    d = out / f"{it['code']}_{it['day'].replace('/', '')}"
    d.mkdir(parents=True, exist_ok=True)
    parts, lines = [], []
    for k, s in enumerate(script(it)):
        img, mp3, mp4 = d / f"s{k}.png", d / f"s{k}.mp3", d / f"s{k}.mp4"
        frame(it, s, img)
        asyncio.run(speak(s["say"], mp3))
        # 정지 화면 + 음성(끝에 0.35초 여유), 30fps·유튜브 권장 H.264/AAC
        dur = float(subprocess.run([FFMPEG, "-i", str(mp3)], capture_output=True, text=True).stderr.split("Duration: ")[1].split(",")[0].split(":")[2]) + 0.35
        run([FFMPEG, "-y", "-loop", "1", "-i", str(img), "-i", str(mp3), "-af", "apad", "-t", f"{dur:.2f}",
             "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k", str(mp4)])
        parts.append(mp4); lines.append(s["say"])
    lst = d / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    mp4 = out / f"{it['name']}_{it['day'].replace('/', '')}_저항선.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(mp4)])
    (out / f"{it['name']}_{it['day'].replace('/', '')}_대본.txt").write_text(
        f"제목: {it['name']} {it['chg']:+.2f}% {script(it)[0]['cap'].splitlines()[1]} 선 3개로 보는 저항·지지 #shorts\n\n" + "\n\n".join(lines) +
        "\n\n※ 사실과 숫자를 정리한 자료이며 매수·매도 권유가 아닙니다. 실시간 추세 판단: https://trlab.net\n", encoding="utf-8")
    return mp4


def pick(groups: list[dict], cc: str, n: int = 3) -> list[dict]:
    """그날 가장 많이 움직인 종목 2개 + 돌파 확인 종목(최대 n개). 지수·선물·상장 초기 카드·이상치(±30% 넘음, 11/20 샌디스크 +678%)는 뺀다."""
    pool = []
    for g in groups:
        if g.get("cc") != cc:
            continue
        for it in g["items"]:
            if not it.get("day") or len(it.get("rows") or []) < 10 or it.get("stale") or it.get("reference_only"):
                continue
            if "=" in str(it.get("code")) or not it.get("channel_valid", True) or not it.get("ma5") or abs(it.get("chg") or 0) >= 30:
                continue
            if abs(it["rows"][-1][4] / it["rows"][-2][4] - 1) >= 0.3:
                continue
            pool.append(it)
    if not pool:
        return []
    last = max(i["day"] for i in pool)                   # 그 시장의 마지막 거래일만(지난 날 값은 안 씀)
    pool = [i for i in pool if i["day"] == last]
    top = sorted(pool, key=lambda i: -abs(i["chg"]))[:2]
    top += [i for i in pool if i.get("state") == "돌파 확인" and i not in top]
    return top[:n]


def daily(cc: str) -> list[Path]:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import chan
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    out = OUT / now.strftime("%Y%m%d")
    out.mkdir(parents=True, exist_ok=True)
    made, log = [], []
    for it in pick(chan.build()["groups"], cc):
        try:
            made.append(build(it, out))
            log.append(f"OK {it['name']} {it['chg']:+.2f}% {it.get('state')}")
        except Exception as e:  # noqa: BLE001
            log.append(f"실패 {it.get('name')}: {type(e).__name__}: {e}")
    with (out / "_기록.txt").open("a", encoding="utf-8") as f:
        f.write(f"[{now:%H:%M} {cc}] " + (" / ".join(log) or "만들 종목 없음") + "\n")
    return made


if __name__ == "__main__":
    if sys.stdout:                                       # pythonw(예약 작업)는 stdout 이 없다
        sys.stdout.reconfigure(encoding="utf-8")
    if "--daily" in sys.argv:
        for p in daily(sys.argv[sys.argv.index("--daily") + 1]):
            print(p)
        sys.exit(0)
    code = sys.argv[1] if len(sys.argv) > 1 else "000660"
    if "--json" in sys.argv:
        it = json.loads(Path(sys.argv[sys.argv.index("--json") + 1]).read_text(encoding="utf-8"))
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import chan
        it = next(i for g in chan.build()["groups"] for i in g["items"] if i.get("code") == code)
    print(build(it))
