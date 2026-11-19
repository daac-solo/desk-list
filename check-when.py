#!/usr/bin/env python3
"""Does the parser take what it should, and leave what it should?

The dangerous failure here is not "it did not understand". It is "it
understood something you did not write" — it eats a word out of your task
title and files the thing under a date you never picked. So the cases
that must NOT match get as many tests as the ones that must.

Run: python3 check-when.py
"""
from datetime import date, datetime
import when as W

T = date(2026, 11, 18)                    # a Wednesday
NOW = datetime(2026, 11, 18, 8, 0)        # 08:00 —— 写死，否则"下午3点"
                                          # 在午饭前过、午饭后挂
bad = 0


def ok(text, title, iso, clock, note=""):
    global bad
    t, d, c, eaten = W.parse(text, today=T, now=NOW)
    good = (t == title and d == iso and c == clock)
    bad += not good
    mark = "✅" if good else "❌"
    print(f"  {mark} {text!r:30} → {t!r} {d or '-'} {c or '-'}"
          + ("" if good else f"   期待 {title!r} {iso or '-'} {clock or '-'}")
          + (f"   {note}" if note and good else ""))


print("今天是 2026-11-18（周三）08:00\n")
print("— 相对日 —")
ok("交电费 今天",      "交电费", "2026-11-18", "")
ok("交电费 明天",      "交电费", "2026-11-19", "")
ok("交电费 后天",      "交电费", "2026-11-20", "")
ok("pay rent tomorrow", "pay rent", "2026-11-19", "")

print("\n— 周几：取将来那个，不是今天 —")
ok("约牙医 周四",      "约牙医", "2026-11-19", "")
ok("约牙医 周三",      "约牙医", "2026-11-25", "", "今天就是周三 → 下个周三")
ok("约牙医 下周三",    "约牙医", "2026-11-25", "")
ok("约牙医 星期日",    "约牙医", "2026-11-22", "")

print("\n— 日期 —")
ok("体检 12/3",        "体检", "2026-12-03", "")
ok("体检 11月20日",     "体检", "2026-11-20", "")
ok("体检 1/5",         "体检", "2027-01-05", "", "已过今年 → 明年")

print("\n— 时间 —")
ok("开会 下午3点",      "开会", "2026-11-18", "15:00")
ok("开会 明天 9:30",    "开会", "2026-11-19", "09:30")
ok("standup 10am",     "standup", "2026-11-18", "10:00")
ok("dinner 7pm",       "dinner", "2026-11-18", "19:00")
ok("开会 15:00",        "开会", "2026-11-18", "15:00", "裸 H:MM 带冒号就是时间")
ok("meeting 9:05",     "meeting", "2026-11-18", "09:05")

print("\n— 不该动的（最要紧的一组）—")
ok("周一的会议纪要",     "周一的会议纪要", "", "", "时间词在句中，不是截止")
ok("明天会更好",        "明天会更好", "", "")
ok("买 3 个苹果",       "买 3 个苹果", "", "", "裸数字不是时间")
ok("读完第 12 章",      "读完第 12 章", "", "")
ok("明天",             "明天", "", "", "整句就是日期 → 当成任务名，别留空任务")
ok("周五",             "周五", "", "")
ok("交电费",           "交电费", "", "")
ok("",                 "", "", "")
ok("13/45",            "13/45", "", "", "不存在的月日")

print("\n— 标签 —")
for iso, clock, want in [("2026-11-18","","今天"), ("2026-11-19","","明天"),
                         ("2026-11-20","","后天"), ("2026-11-22","","周日"),
                         ("2026-12-25","","12/25"), ("2026-11-17","","昨天"),
                         ("2026-11-10","","逾期"), ("2026-11-19","09:30","明天 09:30")]:
    got = W.label(iso, clock, today=T)
    good = got == want
    bad += not good
    print(f"  {'✅' if good else '❌'} {iso} {clock or '':5} → {got!r}" + ("" if good else f"  期待 {want!r}"))

print("\n— 状态 —")
for iso, want in [("2026-11-17","overdue"), ("2026-11-18","today"), ("2026-11-30","later")]:
    got = W.state(iso, today=T)
    good = got == want
    bad += not good
    print(f"  {'✅' if good else '❌'} {iso} → {got}")

print("\n— 一点就定的三个 —")
for lab, iso in W.offers(today=T):
    print(f"  {lab} → {iso}")
_off = dict(W.offers(today=T))
for lab, want in [("今天","2026-11-18"), ("明天","2026-11-19"), ("周六","2026-11-21")]:
    good = _off.get(lab) == want
    bad += not good
    print(f"  {'✅' if good else '❌'} {lab} = {_off.get(lab)}" + ("" if good else f"  期待 {want}"))

print("\n— 三个一点就定的，在一周七天里都必须是三个不同的日子 —")
for _d in range(16, 23):
    _t = date(2026, 11, _d)
    _o = W.offers(today=_t)
    _isos = [i for _l, i in _o]
    _labs = [l for l, _i in _o]
    _uniq = len(set(_isos)) == 3 and len(set(_labs)) == 3
    bad += not _uniq
    print(f"  {'✅' if _uniq else '❌'} 11/{_d} 周{'一二三四五六日'[_t.weekday()]}"
          f"  {_labs}  {[i[5:] for i in _isos]}")

print("\n— 优先级：同样是从你打的字里读 —")
for _t, _want in [("买牛奶!", ("买牛奶",1)), ("买牛奶 !!", ("买牛奶",2)),
                  ("交房租！", ("交房租",1)), ("普通的一条", ("普通的一条",0)),
                  ("!", ("!",0)), ("！！", ("！！",0)),
                  ("买 3 个!", ("买 3 个",1)), ("", ("",0))]:
    _got = W.priority(_t)
    _ok = _got == _want
    bad += not _ok
    print(f"  {'✅' if _ok else '❌'} {_t!r:14} → {_got}" + ("" if _ok else f"  期待 {_want}"))
for _l, _m in [(0,""),(1,"!"),(2,"!!"),(9,"!!"),(-1,"")]:
    _ok = W.mark(_l) == _m
    bad += not _ok
    print(f"  {'✅' if _ok else '❌'} mark({_l}) = {W.mark(_l)!r}")

print(f"\n{'全部通过' if not bad else str(bad) + ' 项失败'}")
raise SystemExit(1 if bad else 0)
