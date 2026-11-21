"""고정 문구 번역표(i18n-ui.js) 점검 — 2026-11-21 운영자: '한 글자도 빠짐없이, 중국어·일본어 등도 모두'.

1) 표의 모든 문구에 6개 화면 언어(en·ja·zh-hans·zh-hant·fr) 번역이 있고, 숫자 자리표 {0}…·요일 {w}가 원문과 같은지
2) index.html·study.html 에 직접 쓴 한국어 문구(스크립트·translate=no 밖)가 모두 표에 있는지
   → 새 문구를 HTML 에 넣고 번역을 안 넣으면 이 테스트가 깨진다. 화면에서 동적으로 만드는 문구는 tests/browser_i18n_check.py 가 본다.
"""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGS = ("en", "ja", "zh-hans", "zh-hant", "fr")
NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
HANGUL = re.compile(r"[가-힣]")


def load_ui():
    src = (ROOT / "i18n-ui.js").read_text(encoding="utf-8")
    ui = json.loads(src.split("window.TRL_UI = ", 1)[1].split(";\nwindow.TRL_WEEK", 1)[0])
    week = json.loads(src.split("window.TRL_WEEK = ", 1)[1].rsplit(";", 1)[0])
    return ui, week


def keys_for(text):
    t = re.sub(r"\s+", " ", text).strip()
    n = iter(range(99))
    tpl = NUMBER.sub(lambda m: "{%d}" % next(n), t)
    tpl = re.sub(r"\((월|화|수|목|금|토|일)\)", "({w})", tpl)
    exact = re.sub(r"\((월|화|수|목|금|토|일)\)", "({w})", t)
    return exact, tpl


class Texts(HTMLParser):
    SKIP = {"script", "style", "noscript", "select", "option", "template"}

    def __init__(self):
        super().__init__()
        self.stack, self.out = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        skip = tag in self.SKIP or a.get("translate") == "no" or "notranslate" in (a.get("class") or "")
        if tag not in ("br", "img", "input", "meta", "link", "hr", "source"):
            self.stack.append(skip)
        if not any(self.stack):
            for name in ("title", "aria-label", "placeholder", "alt"):
                if a.get(name) and HANGUL.search(a[name]):
                    self.out.append(a[name])

    def handle_endtag(self, tag):
        if tag not in ("br", "img", "input", "meta", "link", "hr", "source") and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if not any(self.stack) and HANGUL.search(data):
            self.out.append(data)


def ok_segment(ui, text):
    exact, tpl = keys_for(text)
    if exact in ui or tpl in ui:
        return True
    lead = re.match(r"^[▲▼△⬆⬇⚡•·]\s*", tpl)
    return bool(lead and tpl[lead.end():] in ui)


def covered(ui, text):
    if ok_segment(ui, text):
        return True
    parts = re.split(r"\s+·\s+|^·\s+|\s+·$", text.strip())
    return len(parts) > 1 and all(not HANGUL.search(p) or ok_segment(ui, p) for p in parts)


class I18nUI(unittest.TestCase):
    def test_every_entry_has_all_languages(self):
        ui, week = load_ui()
        self.assertGreater(len(ui), 250)
        for ko, tr in ui.items():
            want = sorted(re.findall(r"\{(?:\d+|w)\}", ko))
            for lang in LANGS:
                self.assertTrue(tr.get(lang), f"{lang} 번역 없음: {ko}")
                self.assertEqual(sorted(re.findall(r"\{(?:\d+|w)\}", tr[lang])), want, f"{lang} 자리표 다름: {ko}")
                self.assertFalse(HANGUL.search(tr[lang]), f"{lang} 번역에 한글이 남음: {ko}")
        for day in "월화수목금토일":
            for lang in LANGS:
                self.assertTrue(week[day][lang])

    def test_static_html_is_covered(self):
        ui, _ = load_ui()
        missing = []
        for page in ("index.html", "study.html"):
            p = Texts()
            html = (ROOT / page).read_text(encoding="utf-8")
            body = html[html.index("<body"):]
            p.feed(body)
            for text in p.out:
                t = re.sub(r"\s+", " ", text).strip()
                if t and not covered(ui, t):
                    missing.append(f"{page}: {t[:80]}")
        self.assertEqual(missing, [], "번역표(i18n-ui.js)에 없는 한국어 문구:\n" + "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
