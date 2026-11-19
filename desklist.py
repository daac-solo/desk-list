#!/usr/bin/env python3
"""桌面清单 — a task list that stays on the desktop.

Separate from 瞭望鸡 on purpose. That one is an inbox: you write a thought
and ⇧⌘⏎ sends it upstream, and the thing it wants most is to be empty.
This is a workspace. A finished task does not vanish, it gets a line drawn
through it and stays, because seeing what you got done is the point.

  ⌃⌘L   show / hide
  ⏎     one line, one task (paste five lines, get five tasks)
  ⎋     clear the field
  click the circle to finish; the line draws through the text
"""

import warnings

import AppKit
import objc
import rumps

# CGColorRef is opaque, so PyObjC cannot introspect it and says so on every
# layer colour. Benign, and loud enough to bury a real warning.
warnings.filterwarnings("ignore", category=objc.ObjCPointerWarning)
from Foundation import NSMakeRect, NSObject

import deskkit as k
import tasks as store
# Not `as W`: W is already the panel width in this file, and
# timeword.parse() on an int throws inside a PyObjC delegate, where the
# traceback is swallowed — every keystroke failed with one
# opaque line in the log. Same shape as the duplicate addDays.
import when as timeword

APP = "desk-list"
# Sharper than the first pass. The soft version was a glass slab: 20pt
# corners, 32pt rows, nothing between them. Everything blurred into one
# shape and the list read as a texture rather than as rows.
#
# Sharp here is not thin. It is: a tighter corner so the panel has an
# edge, rows that touch a hairline so the eye can count them, and one
# number per row set in tabular figures so the column is a column.
W = 320
PAD = 14
ROW = 28
RULE = 0.5        # the hairline between rows; 1 physical pixel at 2dppx
CHIPS = 28        # the offer row — only on screen while you are writing
T1, T2, T3 = k.SIZES[:3]      # 11 / 13 / 17 — the widget row of the scale
MAX_ROWS = 10                 # beyond this the list scrolls

# The placeholder is the only instruction this app has, so it teaches by
# shape rather than by sentence: you see where the time goes, you do not
# read about it. It rotates because one example teaches one form, and
# there are four worth knowing.
#
# This exists because the feature was invisible. Typing a time worked
# from the first build and nobody could have known — the same mistake as
# a shortcut printed nowhere, which this codebase has now made twice.
HINTS = [
    "约牙医 周四 ⏎",
    "交房租 明天 ⏎",
    "standup 10am ⏎",
    "体检 12/3 ⏎",
]


class RowView(AppKit.NSView):
    """One row, so it can know the pointer is over it.

    The delete button only appears on hover. On a desktop widget that is
    fine — there is always a pointer — and it keeps a four-column row from
    carrying a button you press once a week.
    """

    def initWithFrame_(self, frame):
        self = objc.super(RowView, self).initWithFrame_(frame)
        if self is not None:
            self.kill = None
            self.hot = False
            self.tint = None
        return self

    def updateTrackingAreas(self):
        for a in list(self.trackingAreas()):
            self.removeTrackingArea_(a)
        opts = (AppKit.NSTrackingMouseEnteredAndExited
                | AppKit.NSTrackingActiveAlways
                | AppKit.NSTrackingInVisibleRect)
        self.addTrackingArea_(
            AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(), opts, self, None))
        objc.super(RowView, self).updateTrackingAreas()

    def _paint(self):
        if self.kill is not None:
            self.kill.setHidden_(not self.hot)
        if self.tint is not None:
            self.layer().setBackgroundColor_(
                self.tint.CGColor() if self.hot else None)

    def mouseEntered_(self, _e):
        self.hot = True
        self._paint()

    def mouseExited_(self, _e):
        self.hot = False
        self._paint()


def _centered():
    ps = AppKit.NSMutableParagraphStyle.alloc().init()
    ps.setAlignment_(AppKit.NSTextAlignmentCenter)
    return ps


class Offer(NSObject):
    """One date chip. Holds the date it stands for, so the click knows."""

    def initWithISO_owner_(self, iso, owner):
        self = objc.super(Offer, self).init()
        if self is not None:
            self.iso = iso
            self.owner = owner
        return self

    def pick_(self, _sender):
        self.owner.choose(self.iso)


class More(NSObject):
    """The ··· chip: a month, for the days the three offers cannot say.

    NSDatePicker, not a hand-drawn grid of buttons. It already knows about
    months, locales, the first day of the week and the keyboard — all of
    which a rebuilt calendar gets subtly wrong, and none of which is what
    this app is about.
    """

    def initWithOwner_(self, owner):
        self = objc.super(More, self).init()
        if self is not None:
            self.owner = owner
            self.pop = None
            self.picker = None
            self.clock = None
        return self

    def open_(self, sender):
        pal = k.palette(k.is_dark())
        pick = AppKit.NSDatePicker.alloc().initWithFrame_(
            NSMakeRect(0, 0, 139, 148))
        pick.setDatePickerStyle_(AppKit.NSDatePickerStyleClockAndCalendar)
        pick.setDatePickerElements_(AppKit.NSDatePickerElementFlagYearMonthDay)
        # setBordered_ alone leaves the bezel: the control still draws a
        # heavy framed box that belongs to no part of this app.
        pick.setBordered_(False)
        pick.setBezeled_(False)
        # That heavy blue frame is the focus ring, not a border — the
        # picker takes first responder inside the popover and AppKit draws
        # it a box. setBordered_/setBezeled_ never touched it.
        pick.setFocusRingType_(AppKit.NSFocusRingTypeNone)
        pick.setDrawsBackground_(False)
        pick.setTextColor_(pal["fg"])
        # 11月 and 日一二三四五六, not Nov and Su Mo Tu. The control knows
        # how; it just needs to be told whose calendar this is.
        try:
            pick.setLocale_(AppKit.NSLocale.alloc().initWithLocaleIdentifier_("zh_CN"))
        except Exception:
            pass
        try:
            pick.setDateValue_(AppKit.NSDate.date())
        except Exception:
            pass
        pick.setTarget_(self)
        pick.setAction_("picked:")
        self.picker = pick

        # And a time, because "明天" is often "明天几点". Textual, not a
        # clock face: you know the hour, you should be able to type it.
        clock = AppKit.NSDatePicker.alloc().initWithFrame_(
            NSMakeRect(0, 0, 70, 20))
        clock.setDatePickerStyle_(AppKit.NSDatePickerStyleTextField)
        clock.setDatePickerElements_(AppKit.NSDatePickerElementFlagHourMinute)
        clock.setBordered_(False)
        clock.setBezeled_(False)
        clock.setDrawsBackground_(False)
        clock.setFocusRingType_(AppKit.NSFocusRingTypeNone)
        clock.setTextColor_(pal["accent"] if self.owner.pending_clock else pal["muted"])
        clock.setFont_(k.font(T2))
        cal = AppKit.NSCalendar.currentCalendar()
        comps = AppKit.NSDateComponents.alloc().init()
        hh, mm = ((int(x) for x in self.owner.pending_clock.split(":"))
                  if self.owner.pending_clock else (9, 0))
        comps.setYear_(2026); comps.setMonth_(1); comps.setDay_(1)
        comps.setHour_(hh); comps.setMinute_(mm)
        try:
            clock.setDateValue_(cal.dateFromComponents_(comps))
        except Exception:
            pass
        clock.setTarget_(self)
        clock.setAction_("clocked:")
        self.clock = clock

        none = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 34, 20))
        none.setBordered_(False)
        an = AppKit.NSMutableAttributedString.alloc().initWithString_("不限")
        an.addAttribute_value_range_(AppKit.NSForegroundColorAttributeName,
                                     pal["muted"], (0, 2))
        an.addAttribute_value_range_(AppKit.NSFontAttributeName, k.font(T1), (0, 2))
        none.setAttributedTitle_(an)
        none.setTarget_(self)
        none.setAction_("noclock:")

        vc = AppKit.NSViewController.alloc().init()
        host = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 163, 210))
        pick.setFrame_(NSMakeRect(12, 50, 139, 148))
        host.addSubview_(pick)

        line = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(12, 40, 139, RULE))
        line.setWantsLayer_(True)
        line.layer().setBackgroundColor_(
            pal["muted"].colorWithAlphaComponent_(0.25).CGColor())
        host.addSubview_(line)

        clock.setFrame_(NSMakeRect(12, 12, 70, 20))
        none.setFrame_(NSMakeRect(113, 12, 38, 20))
        host.addSubview_(clock)
        host.addSubview_(none)
        vc.setView_(host)

        pop = AppKit.NSPopover.alloc().init()
        pop.setContentViewController_(vc)
        pop.setBehavior_(AppKit.NSPopoverBehaviorTransient)
        # Follow the widget, not the system: 夜山 is a choice this app made.
        pop.setAppearance_(AppKit.NSAppearance.appearanceNamed_(
            AppKit.NSAppearanceNameVibrantDark if k.is_dark()
            else AppKit.NSAppearanceNameVibrantLight))
        pop.setContentSize_(AppKit.NSMakeSize(163, 210))
        self.pop = pop
        pop.showRelativeToRect_ofView_preferredEdge_(
            sender.bounds(), sender, AppKit.NSRectEdgeMaxY)

    def clocked_(self, sender):
        d = sender.dateValue()
        c = AppKit.NSCalendar.currentCalendar().components_fromDate_(
            AppKit.NSCalendarUnitHour | AppKit.NSCalendarUnitMinute, d)
        self.owner.pending_clock = "%02d:%02d" % (c.hour(), c.minute())
        # A time with no day means today — picking 3pm and nothing else
        # should not file the task under no date at all.
        if not self.owner.pending:
            self.owner.pending = timeword.offers()[0][1]
        self.owner.refresh()

    def noclock_(self, _sender):
        self.owner.pending_clock = ""
        if self.pop is not None:
            self.pop.performClose_(None)
        self.owner.refresh()

    def picked_(self, sender):
        d = sender.dateValue()
        cal = AppKit.NSCalendar.currentCalendar()
        c = cal.components_fromDate_(
            AppKit.NSCalendarUnitYear | AppKit.NSCalendarUnitMonth
            | AppKit.NSCalendarUnitDay, d)
        iso = "%04d-%02d-%02d" % (c.year(), c.month(), c.day())
        if self.pop is not None:
            self.pop.performClose_(None)
        self.owner.choose(iso, toggle=False)


class Row(NSObject):
    """One task. Owns its own circle so the click knows which task it is."""

    def initWithIndex_owner_(self, i, owner):
        self = objc.super(Row, self).init()
        if self is not None:
            self.i = i
            self.owner = owner
            self.ink = None
            self.ink_w = 0
        return self

    def toggle_(self, _sender):
        self.owner.toggle(self.i)

    def kill_(self, _sender):
        self.owner.remove(self.i)

    def untime_(self, _sender):
        self.owner.untime(self.i)


class Widget(object):
    def __init__(self):
        self.items = store.load()
        self.shut = False
        self.panel = None
        self.ground = None
        self.field = None
        self.ghost = None
        self.hint = 0
        self._at = None
        # The date chosen for the line being written, before it
        # becomes a task. Cleared on commit and on Escape.
        self.pending = ""
        self.pending_clock = ""
        self.chips = []
        self._writing = False
        self.rows = []
        # Before build(), because render() wires every button to it on its
        # very first line. Building first raised AttributeError inside an
        # NSTimer block, where PyObjC swallows it — the panel came up
        # empty, in the wrong corner, with nothing in the log. Exactly the
        # failure that looks like success.
        self.delegate = Delegate.alloc().initWithWidget_(self)
        self.build()

    # --- the one write path ------------------------------------------
    def commit(self):
        """Every change goes through here, and here is the only place that
        knows whether it landed."""
        if store.save(self.items):
            return True
        self.say("没存上")
        return False

    def say(self, msg):
        if self.field is not None:
            self.field.setPlaceholderString_(msg)

    # --- building -----------------------------------------------------
    def build(self):
        self.panel, self.ground = k.make_panel(W, 300, radius=12)
        self.ground.on_moved = self.moved
        self.render()
        k.place(self.panel, APP)
        self.panel.orderFront_(None)

    def moved(self):
        o = self.panel.frame().origin
        # Nothing moved, nothing to write. A save that records the place
        # the widget already was is harmless on its own and is also the
        # fingerprint of a drag that never happened.
        if self._at == (o.x, o.y):
            return
        self._at = (o.x, o.y)
        k.save_pos(APP, o.x, o.y)

    def reflow(self, raw):
        """Rebuild for the offer row appearing or leaving, and put the
        caret back where it was.

        render() replaces the field, so this would otherwise eat the
        keystroke that triggered it. It runs twice per line — on the first
        character and when the line is cleared — not on every key.
        """
        self.render()
        if self.field is None:
            return
        self.field.setStringValue_(raw)
        self.focus()
        ed = self.panel.fieldEditor_forObject_(False, self.field)
        if ed is not None:
            ed.setSelectedRange_(AppKit.NSMakeRange(len(raw), 0))

    def composing(self):
        """Only while there is something to attach a date to. At rest the
        widget is a list, not a form — which is the whole reason it can
        live on a desktop.

        Reads the flag, not the field. render() rebuilds the field empty
        before this runs, so asking the control said "not writing" every
        time and the offer row reserved its height without ever drawing
        itself.
        """
        return self._writing

    def height(self):
        if self.shut:
            return PAD + T3 + 8 + PAD
        n = max(len(self.items), 1)
        shown = min(n, MAX_ROWS)
        foot = 28 if any(t["ok"] for t in self.items) else 8
        chips = CHIPS if self.composing() else 0
        return PAD + T3 + 10 + 12 + 30 + chips + 6 + shown * ROW + foot + 8

    def render(self):
        pal = k.palette(k.is_dark())
        h = self.height()
        f = self.panel.frame()
        # Grow downward: the title should not walk up the screen as the
        # list gets longer.
        top = f.origin.y + f.size.height
        self.panel.setFrame_display_(
            NSMakeRect(f.origin.x, top - h, W, h), True)
        for v in list(self.ground.subviews()):
            v.removeFromSuperview()
        self.ground.setFrame_(NSMakeRect(0, 0, W, h))
        self.rows = []

        y = h - PAD - T3 - 6
        title = k.label("任务", T3, pal["fg"], AppKit.NSFontWeightSemibold)
        title.setFrame_(NSMakeRect(PAD, y, 120, T3 + 8))
        self.ground.addSubview_(title)

        left = sum(1 for t in self.items if not t["ok"])
        cnt = k.label("还剩 %d" % left if left else "", T1, pal["muted"])
        cnt.setAlignment_(AppKit.NSTextAlignmentRight)
        cnt.setFrame_(NSMakeRect(W - PAD - 24 - 60, y + 3, 60, T1 + 6))
        self.ground.addSubview_(cnt)

        fold = self.button("∨" if self.shut else "∧", T1, pal["muted"],
                           "fold:", NSMakeRect(W - PAD - 24, y + 1, 24, 24))
        fold.setToolTip_("收起" if not self.shut else "展开")
        self.ground.addSubview_(fold)

        if self.shut:
            self.panel.displayIfNeeded()
            return

        y -= 12 + 30
        self.field = k.FocusField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, W - PAD * 2, 30))
        self.field.setFont_(k.font(T2))
        self.field.setTextColor_(pal["fg"])
        self.field.setPlaceholderString_(HINTS[self.hint % len(HINTS)])
        self.field.setBezeled_(False)
        # A hairline, not a fill. A filled field on a glass panel is just
        # another pane of glass; a line is an edge, and an edge is what
        # tells you where you can type.
        self.field.setDrawsBackground_(False)
        self.field.setFocusRingType_(AppKit.NSFocusRingTypeNone)
        self.field.setDelegate_(self.delegate)
        # No box. A rounded rectangle around the one place you type is
        # chrome explaining something the caret already says. One hairline
        # underneath is enough to say "the line is here".
        rule = AppKit.NSView.alloc().initWithFrame_(
            NSMakeRect(PAD, y - 1, W - PAD * 2, RULE))
        rule.setWantsLayer_(True)
        rule.layer().setBackgroundColor_(
            pal["muted"].colorWithAlphaComponent_(0.3).CGColor())
        self.ground.addSubview_(rule)
        self.field.setEditable_(True)
        self.field.setSelectable_(True)
        self.ground.addSubview_(self.field)

        # The guess, shown before it is taken. A parser that silently
        # edits your text is one you stop trusting; this one says what it
        # heard while you are still typing, and you can delete the word if
        # it heard wrong.
        self.ghost = k.label("", T1, pal["accent"])
        self.ghost.setAlignment_(AppKit.NSTextAlignmentRight)
        self.ghost.setFrame_(NSMakeRect(W - PAD - 96 - 10, y + 7, 96, 16))
        self.ghost.setHidden_(True)
        self.ground.addSubview_(self.ghost)

        # The offers. They appear when you start writing and leave when
        # the line does — visible enough that nothing has to be explained,
        # small enough that the widget at rest is still a list.
        self.chips = []
        if self.composing():
            y -= CHIPS
            cx = PAD
            for cap, iso in timeword.offers():
                on = (self.pending == iso)
                btn = AppKit.NSButton.alloc().initWithFrame_(
                    NSMakeRect(cx, y + 2, 40, 22))
                btn.setBordered_(False)
                col = pal["accent"] if on else pal["muted"]
                a = AppKit.NSMutableAttributedString.alloc().initWithString_(cap)
                a.addAttribute_value_range_(AppKit.NSForegroundColorAttributeName,
                                            col, (0, len(cap)))
                a.addAttribute_value_range_(AppKit.NSFontAttributeName,
                                            k.font(T1, AppKit.NSFontWeightSemibold
                                                   if on else AppKit.NSFontWeightRegular),
                                            (0, len(cap)))
                a.addAttribute_value_range_(AppKit.NSParagraphStyleAttributeName,
                                            _centered(), (0, len(cap)))
                btn.setAttributedTitle_(a)
                # Four boxes for four words is four times the chrome the
                # words need. Selection is colour and weight.
                off = Offer.alloc().initWithISO_owner_(iso, self)
                self.chips.append(off)
                btn.setTarget_(off)
                btn.setAction_("pick:")
                self.ground.addSubview_(btn)
                cx += 44

            # Anything the three cannot say.
            picked_other = bool(self.pending) and self.pending not in [
                iso for _c, iso in timeword.offers()]
            col = pal["accent"] if picked_other else pal["muted"]
            cap = timeword.label(self.pending) if picked_other else "···"
            more = AppKit.NSButton.alloc().initWithFrame_(
                NSMakeRect(cx, y + 2, 50 if picked_other else 32, 22))
            more.setBordered_(False)
            am = AppKit.NSMutableAttributedString.alloc().initWithString_(cap)
            am.addAttribute_value_range_(AppKit.NSForegroundColorAttributeName,
                                         col, (0, len(cap)))
            am.addAttribute_value_range_(AppKit.NSFontAttributeName,
                                         k.font(T1, AppKit.NSFontWeightSemibold
                                                if picked_other else AppKit.NSFontWeightRegular),
                                         (0, len(cap)))
            am.addAttribute_value_range_(AppKit.NSParagraphStyleAttributeName,
                                         _centered(), (0, len(cap)))
            more.setAttributedTitle_(am)
            self._more = More.alloc().initWithOwner_(self)
            more.setTarget_(self._more)
            more.setAction_("open:")
            more.setToolTip_("其他日子")
            self.ground.addSubview_(more)

        y -= 8
        if not self.items:
            none = k.label("还没有任务", T2, pal["muted"])
            none.setAlignment_(AppKit.NSTextAlignmentCenter)
            none.setFrame_(NSMakeRect(PAD, y - 40, W - PAD * 2, 24))
            self.ground.addSubview_(none)
            self.panel.displayIfNeeded()
            return

        for i, t in enumerate(self.items[:MAX_ROWS]):
            y -= ROW
            self.row(i, t, y, pal)

        if any(t["ok"] for t in self.items):
            clr = self.button("清掉已完成", T1, pal["muted"], "clear:",
                              NSMakeRect(W - PAD - 80, 10, 80, 24))
            clr.setToolTip_("清掉已完成")
            self.ground.addSubview_(clr)
        self.panel.displayIfNeeded()

    def row(self, i, t, y, pal):
        r = Row.alloc().initWithIndex_owner_(i, self)
        self.rows.append(r)   # ObjC targets are weak. Drop this and the
                              # click stops working the moment Python
                              # collects it — silently, of course.

        rv = RowView.alloc().initWithFrame_(NSMakeRect(PAD - 6, y, W - (PAD - 6) * 2, ROW))
        rv.setWantsLayer_(True)
        rv.layer().setCornerRadius_(6)
        rv.tint = pal["fg"].colorWithAlphaComponent_(0.06)
        self.ground.addSubview_(rv)

        # One hairline under every row but the last. Rows you can count
        # read as a list; rows that float read as a wash.
        if i < min(len(self.items), MAX_ROWS) - 1:
            line = AppKit.NSView.alloc().initWithFrame_(
                NSMakeRect(PAD + 16, y - RULE, W - PAD * 2 - 16, RULE))
            line.setWantsLayer_(True)
            line.layer().setBackgroundColor_(
                pal["muted"].colorWithAlphaComponent_(0.22).CGColor())
            self.ground.addSubview_(line)

        num = k.label(str(i + 1), T1, pal["muted"])
        # Tabular figures: 1 and 10 have to occupy the same width or the
        # column wanders.
        num.setFont_(AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(
            T1, AppKit.NSFontWeightRegular))
        num.setAlignment_(AppKit.NSTextAlignmentRight)
        num.setFrame_(NSMakeRect(0, 5, 16, T1 + 6))
        rv.addSubview_(num)

        # The line goes through the characters, which is the point of
        # finishing something here: it stays on the list, crossed out.
        # Drawn by the text system, not a custom drawRect_ — NSTextField
        # renders through its cell, so a subclass's drawRect_ never ran and
        # the line silently never appeared.
        attrs = {
            AppKit.NSFontAttributeName: k.font(T2),
            AppKit.NSForegroundColorAttributeName:
                pal["muted"] if t["ok"] else pal["fg"],
        }
        body = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            t["text"], attrs)

        avail = W - (PAD - 6) * 2 - 24 - 54
        if t.get("when"):
            _c = k.label(timeword.label(t["when"], t.get("clock", "")), T1, pal["muted"])
            avail -= round(_c.intrinsicContentSize().width) + 18
        tx = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(24, 3, max(avail, 60), 22))
        tx.setAttributedStringValue_(body)
        tx.setBackgroundColor_(AppKit.NSColor.clearColor())
        tx.setBezeled_(False)
        tx.setEditable_(False)
        tx.setSelectable_(False)
        tx.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        tx.setToolTip_(t["text"])
        rv.addSubview_(tx)

        # The line is a layer, not a text attribute.
        #
        # NSStrikethroughStyleAttributeName draws the same line and cannot
        # be animated — it is simply there on the next render. But the line
        # arriving IS the moment this app is about: it is the half second
        # that says the thing is done and still yours. A state that appears
        # fully formed reads as a redraw; a state that draws reads as an
        # event.
        ink = AppKit.CALayer.alloc().init()
        ink.setBackgroundColor_(pal["muted"].CGColor())
        w = body.size().width
        mid = round(tx.frame().size.height / 2.0)
        ink.setFrame_(AppKit.NSMakeRect(0, mid, w if t["ok"] else 0, RULE * 2))
        tx.setWantsLayer_(True)
        tx.layer().addSublayer_(ink)
        r.ink, r.ink_w = ink, w

        x = self.button("✕", T1, pal["muted"], "kill:",
                        NSMakeRect(W - (PAD - 6) * 2 - 52, 2, 24, 24))
        x.setTarget_(r)
        x.setToolTip_("删除")
        x.setHidden_(True)
        rv.addSubview_(x)
        rv.kill = x

        # The chip. It is the word you typed, lifted out of the sentence —
        # which is why there is no date picker anywhere in this app.
        chip_w = 0
        if t.get("when"):
            # Clickable, because the guess can be wrong. Without this the
            # only way to fix a date the parser got from your sentence is
            # to delete the task and type it again — which is what makes
            # people stop using the clever thing.
            cap = timeword.label(t["when"], t.get("clock", ""))
            st = timeword.state(t["when"])
            col = {"overdue": pal["alarm"], "today": pal["accent"]}.get(st, pal["muted"])
            lab = k.label(cap, T1, col)
            chip_w = round(lab.intrinsicContentSize().width) + 4
            holder = AppKit.NSView.alloc().initWithFrame_(
                NSMakeRect(W - (PAD - 6) * 2 - 52 - chip_w, 4, chip_w, 18))
            # The date needs no box either. Overdue is terracotta, today
            # is the accent, later is muted — the colour is the status.
            lab.setAlignment_(AppKit.NSTextAlignmentCenter)
            lab.setFrame_(NSMakeRect(0, 1, chip_w, 15))
            holder.addSubview_(lab)
            holder.setToolTip_("点掉时间")
            hit = AppKit.NSButton.alloc().initWithFrame_(
                NSMakeRect(0, 0, chip_w, 18))
            hit.setBordered_(False)
            hit.setTitle_("")
            hit.setTarget_(r)
            hit.setAction_("untime:")
            holder.addSubview_(hit)
            rv.addSubview_(holder)
            chip_w += 6

        box = AppKit.NSButton.alloc().initWithFrame_(
            NSMakeRect(W - (PAD - 6) * 2 - 24, 2, 24, 24))
        box.setBordered_(False)
        box.setTitle_("")
        box.setTarget_(r)
        box.setAction_("toggle:")
        box.setWantsLayer_(True)
        lay = box.layer()
        lay.setCornerRadius_(12)
        lay.setBorderWidth_(1.0)
        # muted, not the hairline divider colour. This is the one thing on
        # the widget you are meant to click, and WCAG wants 3:1 for that.
        # The divider token measured 1.42:1 — a button too faint to see is
        # the same as no button.
        lay.setBorderColor_((pal["green"] if t["ok"] else pal["muted"]).CGColor())
        if t["ok"]:
            lay.setBackgroundColor_(
                pal["green"].colorWithAlphaComponent_(0.14).CGColor())
            tick = k.label("✓", T2, pal["green"], AppKit.NSFontWeightBold)
            tick.setAlignment_(AppKit.NSTextAlignmentCenter)
            tick.setFrame_(NSMakeRect(0, 3, 24, 18))
            box.addSubview_(tick)
        box.setToolTip_("完成" if not t["ok"] else "取消完成")
        rv.addSubview_(box)

    def button(self, text, size, color, action, frame):
        b = AppKit.NSButton.alloc().initWithFrame_(frame)
        b.setBordered_(False)
        b.setFont_(k.font(size))
        a = AppKit.NSMutableAttributedString.alloc().initWithString_(text)
        a.addAttribute_value_range_(AppKit.NSForegroundColorAttributeName,
                                    color, (0, len(text)))
        a.addAttribute_value_range_(AppKit.NSFontAttributeName,
                                    k.font(size), (0, len(text)))
        b.setAttributedTitle_(a)
        b.setTarget_(self.delegate)
        b.setAction_(action)
        return b

    # --- what the buttons do ------------------------------------------
    def add(self, raw):
        lines = store.split(raw)
        if not lines:
            return
        for text in lines:
            title, iso, clock, _ = timeword.parse(text)
            # A tap beats a guess: if you pressed 明天, that is the answer,
            # whatever the sentence happens to contain.
            if self.pending:
                iso = self.pending
                clock = self.pending_clock or clock
            self.items.append({"text": title, "ok": False, "done_on": "",
                               "when": iso, "clock": clock})
        self.pending = ""
        self.pending_clock = ""
        if self.commit():
            self.hint += 1
            self.render()
            self.focus()

    def toggle(self, i):
        if not (0 <= i < len(self.items)):
            return
        t = self.items[i]
        t["ok"] = not t["ok"]
        t["done_on"] = store.today() if t["ok"] else ""
        if not self.commit():
            t["ok"] = not t["ok"]      # 没存上就别假装存上了
            return
        # Draw the line, then rebuild once it has landed. Rebuilding first
        # would replace the row mid-stroke and the animation would never
        # be seen — which is how it worked before, and why the one moment
        # worth watching was invisible.
        row = self.rows[i] if i < len(self.rows) else None
        ink = getattr(row, "ink", None) if row else None
        if ink is None:
            self.render()
            return
        a = AppKit.CABasicAnimation.animationWithKeyPath_("bounds.size.width")
        a.setFromValue_(ink.bounds().size.width)
        a.setToValue_(row.ink_w if t["ok"] else 0)
        a.setDuration_(0.26)
        a.setTimingFunction_(AppKit.CAMediaTimingFunction.functionWithControlPoints____(
            0.2, 0.0, 0.0, 1.0))
        a.setFillMode_("forwards")
        a.setRemovedOnCompletion_(False)
        ink.addAnimation_forKey_(a, "strike")
        AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            0.30, False, lambda _t: self.render())

    def remove(self, i):
        if not (0 <= i < len(self.items)):
            return
        self.items.pop(i)
        if self.commit():
            self.render()

    def refresh(self):
        raw = self.field.stringValue() if self.field is not None else ""
        self.reflow(raw)

    def choose(self, iso, toggle=True):
        # Pressing the one already chosen takes it off again — otherwise
        # the only way out of a mis-tap is to clear the whole line. The
        # calendar does not toggle: you picked a day, you meant that day.
        self.pending = ("" if self.pending == iso else iso) if toggle else iso
        raw = self.field.stringValue() if self.field is not None else ""
        self.reflow(raw)

    def untime(self, i):
        if not (0 <= i < len(self.items)):
            return
        self.items[i]["when"] = ""
        self.items[i]["clock"] = ""
        if self.commit():
            self.render()

    def clear_done(self):
        self.items = [t for t in self.items if not t["ok"]]
        if self.commit():
            self.render()

    def fold(self):
        self.shut = not self.shut
        self.render()

    def focus(self):
        if self.field is not None:
            k.take_focus(self.panel, self.field)

    def visible(self):
        return bool(self.panel and self.panel.isVisible())

    def show(self, on):
        if on:
            self.panel.orderFront_(None)
            self.focus()
        else:
            self.panel.orderOut_(None)


class App(rumps.App):
    def __init__(self):
        super(App, self).__init__("☑", quit_button=None)
        self.w = None
        self.menu = ["显示 / 隐藏", None, rumps.MenuItem("退出", callback=self.bye)]

    def post(self):
        try:
            self._post()
        except Exception:
            # PyObjC discards anything raised inside a timer block. Without
            # this the app starts, shows nothing, and says nothing.
            import traceback
            traceback.print_exc()
            rumps.notification("桌面清单", "", "启动出错，看终端")

    def _post(self):
        # Without this ⌘V does nothing in the field, silently.
        k.install_menu("退出桌面清单")
        self.w = Widget()
        self.w.focus()
        try:
            from hotkeys import HotKeys, CTRL, CMD
            self.keys = HotKeys()
            ok = self.keys.register("l", CTRL | CMD,
                                    lambda: self.w.show(not self.w.visible()))
            # register() returns False for a key it does not know. Printing
            # the shortcut either way would promise one that does nothing.
            print("hotkeys: ⌃⌘L 显示 / 隐藏" if ok
                  else "hotkeys: ⌃⌘L 没注册上", flush=True)
        except Exception as e:
            print("hotkeys unavailable: %s" % e, flush=True)

    @rumps.clicked("显示 / 隐藏")
    def toggle(self, _):
        if self.w:
            self.w.show(not self.w.visible())

    def bye(self, _):
        rumps.quit_application()


class Delegate(NSObject):
    """One ObjC object the panel's buttons and the field can point at.
    Kept on the Widget so it is not collected while AppKit still holds a
    weak target to it."""

    def initWithWidget_(self, w):
        self = objc.super(Delegate, self).init()
        if self is not None:
            self.w = w
        return self

    def fold_(self, _s):
        self.w.fold()

    def clear_(self, _s):
        self.w.clear_done()

    @objc.python_method
    def _guard(self, fn, *a):
        """PyObjC discards anything raised inside a delegate callback. The
        only symptom is AppKit printing "Exception detected while handling
        key input" — no file, no line, no clue. Never again."""
        try:
            return fn(*a)
        except Exception:
            import traceback
            traceback.print_exc()
            return None

    def controlTextDidChange_(self, note):
        """Two jobs on every keystroke.

        A single-line NSTextField flattens a multi-line paste into one
        string, so "five lines pasted" would have become one very long
        task. And the time guess is shown here rather than on Enter,
        because a guess you only see after committing is not a guess, it
        is a surprise."""
        self._guard(self._changed, note)

    @objc.python_method
    def _changed(self, note):
        control = note.object()
        raw = control.stringValue()
        if "\n" in raw or "\r" in raw:
            control.setStringValue_("")
            self.w.add(raw)
            return
        writing = bool(raw.strip())
        if writing != self.w._writing:
            self.w._writing = writing
            self.w.reflow(raw)
            return
        g = self.w.ghost
        if g is None:
            return
        _title, iso, clock, eaten = timeword.parse(raw)
        if iso and eaten:
            g.setStringValue_("↑ " + timeword.label(iso, clock))
            g.setHidden_(False)
        else:
            g.setHidden_(True)

    def control_textView_doCommandBySelector_(self, control, view, selector):
        return self._guard(self._command, control, view, selector)

    @objc.python_method
    def _command(self, control, view, selector):
        name = selector.name() if hasattr(selector, "name") else str(selector)
        if name == "insertNewline:":
            text = control.stringValue()
            control.setStringValue_("")
            if self.w.ghost is not None:
                self.w.ghost.setHidden_(True)
            self.w._writing = False
            self.w.add(text)
            return True
        if name == "cancelOperation:":
            control.setStringValue_("")
            self.w.pending = ""
            self.w.pending_clock = ""
            if self.w._writing:
                self.w._writing = False
                self.w.reflow("")
            return True
        return False


if __name__ == "__main__":
    app = App()
    AppKit.NSApplication.sharedApplication().setActivationPolicy_(
        AppKit.NSApplicationActivationPolicyAccessory)
    print("桌面清单 starting", flush=True)

    # The panel is built once the run loop is up: rumps has not installed
    # its own app object until then, and NSApp has to exist before a panel
    # can be ordered front.
    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        0.1, False, lambda t: app.post())
    app.run()
