"""Lift a time out of a sentence.

You already type the task. Making you then click a date picker is asking
for the same information twice, so the time is read out of what you wrote
and the words that carried it leave the title: "约牙医 周四" becomes the
task 约牙医 and a chip that says 周四.

Rules that keep it honest:
  - Only the tail. A time word in the middle of a sentence is usually part
    of the sentence ("周一的会议纪要"), not a due date.
  - Nothing is removed unless something was understood.
  - It returns what it matched, so the caller can show the guess before
    committing to it. A parser that edits your text without showing you
    what it took is the one that gets turned off.
"""

import re
from datetime import date, datetime, timedelta

WEEK = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
        "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_DAY = [
    (r"今天|今日|today", 0),
    (r"明天|明日|tomorrow|tmr", 1),
    (r"后天", 2),
    (r"大后天", 3),
]


def _next_weekday(today, target, next_week=False):
    """The coming one. 'Thursday' on a Thursday means next Thursday, not
    today — if you meant today you would have written 今天."""
    delta = (target - today.weekday()) % 7
    if delta == 0:
        delta = 7
    if next_week:
        delta = (target - today.weekday()) % 7 + 7 if delta != 7 else 7
    return today + timedelta(days=delta)


def parse(text, today=None, now=None):
    """-> (title, iso_date or '', clock or '', matched_text)

    matched_text is the slice that was understood, so the UI can show it
    before it is taken away. `now` is injectable because "3pm" means today
    or tomorrow depending on what time it is, and a test that reads the
    wall clock passes in the morning and fails after lunch.
    """
    today = today or date.today()
    now = now or datetime.now()
    s = text.rstrip()
    if not s:
        return text, "", "", ""

    when = None
    clock = ""
    eaten = ""

    # --- clock, always at the very end ---
    m = re.search(r"(?:^|\s)(?:(上午|早上|中午|下午|晚上)\s*)?"
                  r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|点|時|时)?\s*$",
                  s, re.I)
    # A bare number is not a time ("买 3 个苹果"). It needs a marker: a
    # period word, an am/pm/点 suffix, or a colon — 9:30 can only be a clock.
    if m and (m.group(1) or m.group(3) or m.group(4)):
        h = int(m.group(2))
        mi = int(m.group(3) or 0)
        tag = (m.group(4) or "").lower()
        period = m.group(1) or ""
        if tag == "pm" and h < 12:
            h += 12
        elif tag == "am" and h == 12:
            h = 0
        elif period in ("下午", "晚上") and h < 12:
            h += 12
        elif period == "中午" and h < 12:
            h = 12
        if 0 <= h <= 23 and 0 <= mi <= 59:
            clock = "%02d:%02d" % (h, mi)
            eaten = s[m.start():].strip()
            s = s[:m.start()].rstrip()

    # --- day, at the end of what is left ---
    for pat, off in _DAY:
        m = re.search(r"(?:^|\s)(" + pat + r")\s*$", s, re.I)
        if m:
            when = today + timedelta(days=off)
            eaten = (m.group(1) + " " + eaten).strip()
            s = s[:m.start()].rstrip()
            break

    if when is None:
        m = re.search(r"(?:^|\s)(下?)(?:周|週|星期|礼拜)([一二三四五六日天])\s*$", s)
        if m:
            when = _next_weekday(today, WEEK[m.group(2)], next_week=bool(m.group(1)))
            eaten = (m.group(0).strip() + " " + eaten).strip()
            s = s[:m.start()].rstrip()

    if when is None:
        m = re.search(r"(?:^|\s)(\d{1,2})\s*[/月\-]\s*(\d{1,2})\s*日?\s*$", s)
        if m:
            mo, dy = int(m.group(1)), int(m.group(2))
            for yr in (today.year, today.year + 1):
                try:
                    cand = date(yr, mo, dy)
                except ValueError:
                    break
                if cand >= today:
                    when = cand
                    break
            if when:
                eaten = (m.group(0).strip() + " " + eaten).strip()
                s = s[:m.start()].rstrip()

    # A clock with no day means today — or tomorrow if that hour is gone.
    if clock and when is None:
        when = today
        hh, mm = (int(x) for x in clock.split(":"))
        # An hour that has already gone past means tomorrow. Writing
        # "3pm" at five o'clock is not a request to be reminded two
        # hours ago.
        if today == now.date() and (hh, mm) <= (now.hour, now.minute):
            when = today + timedelta(days=1)

    if when is None:
        return text, "", "", ""
    if not s.strip():
        # The whole line was a date. That is not a task, so keep it as one.
        return text, "", "", ""
    return s.strip(), when.isoformat(), clock, eaten


def label(iso, clock="", today=None):
    """How the chip reads. Short, and relative where relative is clearer."""
    if not iso:
        return ""
    today = today or date.today()
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return ""
    gap = (d - today).days
    if gap < 0:
        head = "逾期" if gap < -1 else "昨天"
    elif gap == 0:
        head = "今天"
    elif gap == 1:
        head = "明天"
    elif gap == 2:
        head = "后天"
    elif gap < 7:
        head = "周" + "一二三四五六日"[d.weekday()]
    else:
        head = "%d/%d" % (d.month, d.day)
    return head + (" " + clock if clock else "")


def state(iso, today=None):
    """overdue | today | later — what the chip should be coloured by."""
    if not iso:
        return ""
    today = today or date.today()
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return ""
    return "overdue" if d < today else ("today" if d == today else "later")


# --- the one-tap offers --------------------------------------------------
# Typing "周四" works and always will, but it asks you to know that it
# works. These are the same thing with nothing to know: you see 今天, you
# press 今天. The typed path stays for everything these four cannot say.

def offers(today=None):
    """-> [(label, iso), ...] — today, tomorrow, and the coming weekend."""
    today = today or date.today()
    out = [("今天", today.isoformat()),
           ("明天", (today + timedelta(days=1)).isoformat())]
    # Saturday, unless today is the weekend, in which case next Saturday.
    ahead = (5 - today.weekday()) % 7 or 7
    out.append(("周末", (today + timedelta(days=ahead)).isoformat()))
    return out
