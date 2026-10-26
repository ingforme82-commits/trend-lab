"""2026년 5~10월 스터디 사진을 한 번에 아카이브에 넣는 일회용 스크립트.

  python tools/import_2026.py
사진은 C:\\조영근\\추세 추종 스터디 사진 에서 읽고, 촬영 시각(EXIF)으로 정렬해 study/<id>/에 저장한다.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from study import shrink  # noqa: E402

SRC = Path(r"C:\조영근\추세 추종 스터디 사진")
K = "KakaoTalk_"

# id: (사진 [(파일, 설명)], 대표 사진 파일, 포스터 파일)
PLAN = {
    "2026-05-09": ([
        (K + "20260509_143854559.jpg", "강의 시작 — 화이트보드 앞에서"),
        (K + "20260509_143854559_01.jpg", "화면에 띄운 시황 자료"),
        (K + "20260509_143854559_02.jpg", "실제 차트로 보는 흐름"),
        (K + "20260509_추세추종1.jpg", "첫 모임 참석자들"),
        (K + "20260509_144318103.jpg", "화이트보드 정리"),
    ], K + "20260509_추세추종1.jpg", None),
    "2026-06-20": ([
        (K + "20260620_130207855.jpg", "화이트보드에 정리한 시장 흐름"),
        (K + "20260620_추세추종2.jpg", "6월 스터디 참석자들"),
    ], K + "20260620_추세추종2.jpg", None),
    "2026-07-11": ([
        (K + "20260711_100349727.jpg", "베델회관 7층에서 본 양재 시민의숲"),
        (K + "20260711_135156776.jpg", "화이트보드 — 메모리·AI 흐름 정리"),
        (K + "20260711_추세추종3.jpg", "7월 스터디 참석자들"),
        (K + "20260711_123913450.jpg", "함께 나눈 점심"),
    ], K + "20260711_추세추종3.jpg", None),
    "2026-08-08": ([
        (K + "20260808_122404149.jpg", "손절 케이스 스터디 시작"),
        (K + "20260808_122404149_01.jpg", "오늘의 기준 하나 — 정해둔 규칙대로 실행한 손절"),
        (K + "20260808_122404149_02.jpg", "미니 특강 ① 손절은 세 종류다"),
        (K + "20260808_122404149_03.jpg", "미니 특강 ② 왜 실행이 안 되는가"),
        (K + "20260808_122404149_04.jpg", "미니 특강 ③ 오늘 쓸 공용 언어"),
        (K + "20260808_122404149_05.jpg", "발표 규칙"),
        (K + "20260808_122404149_06.jpg", "발표 양식 — 이 네 가지만"),
        (K + "20260809_132707787.jpg", "케이스 발표"),
        (K + "20260809_132707787_01.jpg", "매매 기록을 화면에 띄워 함께 복기"),
        (K + "20260809_132707787_02.jpg", "발표와 질의응답"),
        (K + "20260809_132707787_03.jpg", "차트를 보며 피드백"),
        (K + "20260809_132707787_04.jpg", "발표 자료"),
        (K + "20260808_122404149_07.jpg", "8월 스터디 참석자들"),
    ], K + "20260808_122404149_07.jpg", K + "20260808_064611945.jpg"),
    "2026-09-12": ([
        (K + "20260912_140648236_01.jpg", "차트에 그은 지지·저항선"),
        (K + "20260912_추세추종5.jpg", "9월 스터디 참석자들"),
        (K + "20260912_140648236_02.jpg", "화이트보드 — 지지와 저항 기준 정리"),
        (K + "20260912_140648236_03.jpg", "케이스 발표 — 내가 그은 선의 근거"),
        (K + "20260912_132816554.jpg", "발표 후 토론"),
    ], K + "20260912_추세추종5.jpg", None),
    "2026-10-17": ([
        (K + "20261017_추세추종.jpg", "10월 스터디 참석자들"),
    ], K + "20261017_추세추종.jpg", None),
    "2026-10-26": ([
        ("성장주 발굴 독서 토론 10권의 책 선정 리스트 공유.jpg", "함께 읽을 10권"),
        (K + "20261026_성장주 발굴 독서 토론 모임.jpg", "첫 독서 토론 참석자들"),
    ], K + "20261026_성장주 발굴 독서 토론 모임.jpg", K + "20261018_141830118.png"),
}


def shot_time(p: Path) -> datetime:
    try:
        ex = Image.open(p).getexif()
        v = ex.get_ifd(0x8769).get(36867) or ex.get(306)
        if v:
            return datetime.strptime(v, "%Y:%m:%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        pass
    s = p.stem.replace(K, "")  # 카톡 파일명: YYYYMMDD_HHMMSS...
    try:
        return datetime.strptime(s[:15], "%Y%m%d_%H%M%S")
    except ValueError:
        return datetime.strptime(s[:8], "%Y%m%d")


def main() -> None:
    data_p = ROOT / "data" / "studies.json"
    items = json.loads(data_p.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in items}
    for sid, (photos, cover, poster) in PLAN.items():
        s = by_id[sid]
        out = ROOT / "study" / sid
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        rows = sorted(((shot_time(SRC / f), f, c) for f, c in photos), key=lambda r: r[0])
        s["photos"] = []
        for i, (t, f, c) in enumerate(rows, 1):
            name = f"{i:02d}.jpg"
            shrink(SRC / f, out / name, 1600, 82)
            shrink(SRC / f, out / f"t_{name}", 520, 78)
            same_day = t.strftime("%Y-%m-%d") == s["date"]
            s["photos"].append({"src": f"study/{sid}/{name}", "thumb": f"study/{sid}/t_{name}", "caption": c,
                                "time": t.strftime("%H:%M") if same_day and t.hour else "",
                                "date": t.strftime("%Y-%m-%d")})
            if f == cover:
                s["cover"] = i - 1
        if poster:
            shrink(SRC / poster, out / "poster.jpg", 1400, 85)
            shrink(SRC / poster, out / "t_poster.jpg", 520, 80)
            s["poster"] = {"src": f"study/{sid}/poster.jpg", "thumb": f"study/{sid}/t_poster.jpg"}
        print(f"{sid}: 사진 {len(rows)}장{' + 포스터' if poster else ''}")
    data_p.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
