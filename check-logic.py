#!/usr/bin/env python3
"""不碰 GUI 的那一半：逻辑、存储、解析、以及所有边界。

GUI 那半在这个环境里测不稳（合成按键和焦点抢时序），所以这里只测
能确定的东西 —— 而这个 app 真正会丢数据的地方全在这一半。
"""
import json, os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import date, datetime, timedelta
import when as W
import tasks as store

bad = 0
def ok(label, want, got):
    global bad
    good = want == got
    bad += not good
    print(f"  {'✅' if good else '❌'} {label}" + ("" if good else f"\n       期待 {want!r}\n       实际 {got!r}"))

T = date(2026, 11, 18)
NOW = datetime(2026, 11, 18, 8, 0)

print("— 存储：丢数据的地方 —")
tmp = tempfile.mkdtemp()
store.FILE = os.path.join(tmp, "t.json")
ok("没有文件时 load 返回空", [], store.load())
ok("save 返回 True", True, store.save([{"text":"a","ok":False,"done_on":"","when":"","clock":""}]))
ok("存了能读回来", "a", store.load()[0]["text"])
ok("时间字段读得回来", ("2026-11-20","09:30"),
   (lambda _: (store.load()[0]["when"], store.load()[0]["clock"]))(
     store.save([{"text":"a","ok":False,"done_on":"","when":"2026-11-20","clock":"09:30"}])))
# 旧格式（没有 when/clock）不能炸
store.save([{"text":"老的","ok":True,"done_on":"2026-01-01"}])
old = store.load()[0]
ok("旧文件没有 when 字段也能读", ("老的", True, "", ""),
   (old["text"], old["ok"], old["when"], old["clock"]))
# 空 text 要被丢掉，不是留一条空任务
store.save([{"text":"  ","ok":False},{"text":"实的","ok":False}])
ok("空白任务被丢掉", ["实的"], [t["text"] for t in store.load()])
# 坏文件
with open(store.FILE,"w") as fh: fh.write("{ 这不是 json")
ok("坏文件返回空而不是抛", [], store.load())
ok("坏文件被挪到 .broken", True, os.path.exists(store.FILE+".broken"))
# 写不进去要返回 False
store.FILE = "/这个目录不存在/x/t.json"
ok("写不进去返回 False", False, store.save([{"text":"a"}]))
shutil.rmtree(tmp, ignore_errors=True)

print("\n— split：一行一条 —")
ok("多行拆开", ["一","二","三"], store.split("一\n二\n三"))
ok("空行丢掉", ["一","二"], store.split("一\n\n  \n二"))
ok("\\r\\n 也算", ["一","二"], store.split("一\r\n二"))
ok("全空返回空", [], store.split("   \n  "))

print("\n— offers 与 label 的一致性 —")
for lab, iso in W.offers(today=T):
    shown = W.label(iso, "", today=T)
    ok(f"点「{lab}」之后牌上显示的也是「{lab}」", lab, shown)

print("\n— 解析的边界 —")
for text, want_title in [
    ("约牙医 周四", "约牙医"),
    ("周四", "周四"),
    ("  ", "  "),
    ("x"*300 + " 明天", "x"*300),
]:
    t, iso, c, _ = W.parse(text, today=T, now=NOW)
    ok(f"{text[:18]!r} 的标题", want_title, t)

t, iso, c, _ = W.parse("开会 2/30", today=T, now=NOW)
ok("2月30日不存在 → 不动", ("开会 2/30", ""), (t, iso))
t, iso, c, _ = W.parse("开会 25:00", today=T, now=NOW)
ok("25 点不存在 → 不动", ("开会 25:00", ""), (t, iso))
ok("label 吃到坏日期返回空", "", W.label("不是日期"))
ok("state 吃到坏日期返回空", "", W.state("不是日期"))
ok("label 吃到空返回空", "", W.label(""))

print(f"\n{'全部通过' if not bad else str(bad) + ' 项失败'}")
sys.exit(1 if bad else 0)
