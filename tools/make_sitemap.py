"""sitemap.xml 만들기(검색 노출용, 서치 콘솔에 등록). publish.py 가 글을 올릴 때마다 함께 실행한다.
하위 경로(github.io/trend-lab/)라 robots.txt 는 검색엔진이 읽지 않으므로 만들지 않는다.

  python tools/make_sitemap.py
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://ingforme82-commits.github.io/trend-lab/"


def main() -> None:
    pages = [("", "hourly", "1.0"), ("study.html", "weekly", "0.6")]
    # 블로그 분석 글(posts/)은 2026-10-28 사이트에서 뺌
    def lastmod(rel: str) -> str:
        f = ROOT / urllib.parse.unquote(rel or "index.html")
        return datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d") if f.exists() else ""
    rows = "\n".join(f"  <url><loc>{BASE}{p}</loc><lastmod>{lastmod(p)}</lastmod><changefreq>{c}</changefreq><priority>{pr}</priority></url>"
                     for p, c, pr in pages)
    (ROOT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}\n</urlset>\n', encoding="utf-8")
    print(f"sitemap.xml {len(pages)}개 주소")


if __name__ == "__main__":
    main()
