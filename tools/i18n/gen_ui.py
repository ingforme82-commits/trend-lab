# 사용: python tools/i18n/gen_ui.py  (ui_dict.py 를 고친 뒤 i18n-ui.js 를 다시 만든다 · pip install opencc-python-reimplemented)
import json, opencc, re, sys, importlib
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parent)); import ui_dict
cc=opencc.OpenCC("s2twp"); out={}
for ko,en,ja,zh,fr in ui_dict.UI:
    if ko in out: continue
    ph=lambda s: sorted(re.findall(r"\{(?:\d+|w)\}",s))
    for v in (en,ja,zh,fr):
        if ph(v)!=ph(ko): print("PH",ko,"|",v)
    out[ko]={"en":en,"ja":ja,"zh-hans":zh,"zh-hant":cc.convert(zh),"fr":fr}
week={k:{"en":v[0],"ja":v[1],"zh-hans":v[2],"zh-hant":cc.convert(v[2]),"fr":v[3]} for k,v in ui_dict.WEEK.items()}
p=str(__import__("pathlib").Path(__file__).resolve().parents[2]/"i18n-ui.js")
head=open(p,encoding="utf-8").read().split("window.TRL_UI = ")[0]
open(p,"w",encoding="utf-8").write(head+"window.TRL_UI = "+json.dumps(out,ensure_ascii=False,indent=0)+";\nwindow.TRL_WEEK = "+json.dumps(week,ensure_ascii=False)+";\n")
print(len(out),"entries")
