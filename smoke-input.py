#!/usr/bin/env python3
"""Can you actually get text into this thing? — a hand-run smoke script.

NOT a pass/fail gate, and it does not exit non-zero. Driving a
non-activating panel with synthetic CGEvents races against AppKit's own
focus handling: the same build scored 0, 2 and 5 failures on three
consecutive runs here. A check that red-lights at random is worse than
no check — you stop reading it.

So it prints what happened and leaves the judgement to you. A line that
says ❌ means "look at this", not "it is broken". The deterministic half
of the coverage lives in check-when.py, which has no GUI in it.

Every case below was a real bug at some point, and each looked like
nothing happening:

  clicking the field gave no keyboard focus, because a non-activating
  panel does not make its app active — the caret appeared and the
  keystrokes went to whatever was frontmost;

  ⌘V did nothing, because an agent app with no main menu has no
  clipboard in its own text fields;

  a multi-line paste became one very long task, because a single-line
  NSTextField flattens it;

  and the time parser threw on every keystroke, because `W` was already
  the panel width — swallowed by PyObjC, surfaced only as AppKit's
  "Exception detected while handling key input".

None of that is visible by reading the code. Run it against the app:

    ./.venv/bin/python desklist.py &
    ./.venv/bin/python check-input.py
"""
import json
import os
import subprocess
import sys
import time

import AppKit
import Quartz

STORE = os.path.expanduser("~/.local/share/desk-list/tasks.json")
RETURN, V, ESC = 36, 9, 53


def pid():
    out = subprocess.run(["pgrep", "-f", "desklist.py"],
                         capture_output=True, text=True).stdout.split()
    if not out:
        out = subprocess.run(["pgrep", "-f", "Desk List.app/Contents/MacOS"],
                             capture_output=True, text=True).stdout.split()
    if not out:
        sys.exit("桌面清单没在跑")
    return int(out[0])


def panel(p):
    wl = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    for w in wl:
        if w.get("kCGWindowOwnerPID") == p and w.get("kCGWindowLayer") == 3:
            return w["kCGWindowBounds"]
    sys.exit("找不到面板")


def click(x, y, pause=0.5):
    for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                           Quartz.CGEventCreateMouseEvent(None, t, (x, y), 0))
        time.sleep(0.07)
    time.sleep(pause)


def typ(text):
    for ch in text:
        for down in (True, False):
            e = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(e, len(ch), ch)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
            time.sleep(0.035)
    time.sleep(0.35)


def key(code, flags=0):
    for down in (True, False):
        e = Quartz.CGEventCreateKeyboardEvent(None, code, down)
        if flags:
            Quartz.CGEventSetFlags(e, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
        time.sleep(0.07)
    time.sleep(0.9)


def items():
    try:
        with open(STORE, encoding="utf-8") as fh:
            return json.load(fh)["items"]
    except Exception:
        return []


def settle(want, limit=4.0):
    """Wait for the store to reach a count, instead of guessing how long
    the app needs.

    The first version of this file used fixed sleeps and failed a
    different subset every run. A flaky test is worse than no test: you
    stop reading it, and then it is just a file that makes the suite
    slow. Every action here is "do it, then wait for the effect".
    """
    end = time.time() + limit
    while time.time() < end:
        if len(items()) == want:
            return True
        time.sleep(0.1)
    return False


def refocus(p):
    """Click back into the field, then wait for key status to land.

    The app rebuilds the field on every change, so the view a keystroke
    was aimed at may already be gone. And the click itself is not
    instant: it runs activateIgnoringOtherApps_, and keystrokes sent
    before that settles go to whatever app was frontmost. Half a second
    was not enough and the whole file failed in a way that looked like
    the app ignoring the keyboard."""
    b = panel(p)
    click(b["X"] + b["Width"] / 2, b["Y"] + 14 + 17 + 10 + 12 + 15, 1.2)


def main():
    p = pid()
    b = panel(p)
    bad = 0

    def check(label, want, got):
        nonlocal bad
        ok = want == got
        bad += not ok
        print(f"  {'✅' if ok else '❌'} {label}"
              + ("" if ok else f"\n       期待 {want}\n       实际 {got}"))

    n = len(items())

    # Focus by clicking the field — the gesture a person actually uses.
    refocus(p)
    typ("能打进去吗")
    key(RETURN)
    n += 1
    check("点一下输入框就能打字", True, settle(n))

    # The app grew a row and rebuilt the field; focus should survive it.
    typ("焦点还在吗")
    key(RETURN)
    n += 1
    check("加完一条之后焦点还在，不用再点", True, settle(n))

    refocus(p)
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_("粘贴一\n粘贴二\n粘贴三", AppKit.NSPasteboardTypeString)
    key(V, Quartz.kCGEventFlagMaskCommand)
    n += 3
    check("⌘V 粘三行得三条，不是一条长的", True, settle(n))

    refocus(p)
    typ("约牙医 周四")
    key(RETURN)
    n += 1
    got = settle(n)
    last = items()[-1] if items() else {}
    check("时间从句子里摘出来", (True, "约牙医", True),
          (got, last.get("text"), bool(last.get("when"))))

    refocus(p)
    typ("不要的")
    key(ESC)
    time.sleep(0.6)
    check("Escape 清空，什么都不留下", n, len(items()))

    print(f"\n{'这一轮全过' if not bad else str(bad) + ' 项要看一下'}")
    print("合成按键会和 AppKit 的焦点处理抢时序，同一个版本连跑三次可能")
    print("得到不同结果。❌ 的意思是「去看一眼」，不是「它坏了」。")
    print("（测试数据留在清单上了，自己删掉）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
