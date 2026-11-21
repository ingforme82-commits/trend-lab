"""sitemap.xml 만들기(검색 노출용, 서치 콘솔에 등록). publish.py 가 글을 올릴 때마다 함께 실행한다.
11/19부터 trlab.net(루트 도메인) — robots.txt 는 저장소 루트에 고정 파일로 둔다(Sitemap 위치 안내).

  python tools/make_sitemap.py
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://trlab.net/"


def main() -> None:
    pages = [("", "hourly", "1.0"), ("study.html", "weekly", "0.6"), ("en/", "weekly", "0.8")]
    # 블로그 분석 글(posts/)은 2026-10-28 사이트에서 뺌
    def lastmod(rel: str) -> str:
        f = ROOT / urllib.parse.unquote(rel + "index.html" if not rel or rel.endswith("/") else rel)
        return datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d") if f.exists() else ""
    rows = "\n".join(f"  <url><loc>{BASE}{p}</loc><lastmod>{lastmod(p)}</lastmod><changefreq>{c}</changefreq><priority>{pr}</priority></url>"
                     for p, c, pr in pages)
    (ROOT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}\n</urlset>\n', encoding="utf-8")
    print(f"sitemap.xml {len(pages)}개 주소")


if __name__ == "__main__":
    main()
