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

APP = "desk-list"
W = 320
PAD = 16
ROW = 32
T1, T2, T3 = k.SIZES          # 11 / 13 / 17 — three on a screen, counted
MAX_ROWS = 10                 # beyond this the list scrolls


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


class Row(NSObject):
    """One task. Owns its own circle so the click knows which task it is."""

    def initWithIndex_owner_(self, i, owner):
        self = objc.super(Row, self).init()
        if self is not None:
            self.i = i
            self.owner = owner
        return self

    def toggle_(self, _sender):
        self.owner.toggle(self.i)

    def kill_(self, _sender):
        self.owner.remove(self.i)


class Widget(object):
    def __init__(self):
        self.items = store.load()
        self.shut = False
        self.panel = None
        self.ground = None
        self.field = None
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
        self.panel, self.ground = k.make_panel(W, 300)
        self.ground.on_moved = self.moved
        self.render()
        k.place(self.panel, APP)
        self.panel.orderFront_(None)

    def moved(self):
        o = self.panel.frame().origin
        k.save_pos(APP, o.x, o.y)

    def height(self):
        if self.shut:
            return PAD + T3 + 10 + PAD
        n = max(len(self.items), 1)
        shown = min(n, MAX_ROWS)
        foot = 28 if any(t["ok"] for t in self.items) else 8
        return PAD + T3 + 10 + 12 + 32 + 8 + shown * ROW + foot + 8

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

        y -= 12 + 32
        self.field = k.FocusField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, W - PAD * 2, 32))
        self.field.setFont_(k.font(T2))
        self.field.setTextColor_(pal["fg"])
        self.field.setPlaceholderString_("写一行，回车")
        self.field.setBezeled_(False)
        self.field.setDrawsBackground_(True)
        self.field.setBackgroundColor_(pal["fg"].colorWithAlphaComponent_(0.04))
        self.field.setFocusRingType_(AppKit.NSFocusRingTypeNone)
        self.field.setDelegate_(self.delegate)
        self.field.setWantsLayer_(True)
        self.field.layer().setCornerRadius_(8)
        self.field.setEditable_(True)
        self.field.setSelectable_(True)
        self.ground.addSubview_(self.field)

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

        rv = RowView.alloc().initWithFrame_(NSMakeRect(8, y, W - 16, ROW))
        rv.setWantsLayer_(True)
        rv.layer().setCornerRadius_(8)
        rv.tint = pal["fg"].colorWithAlphaComponent_(0.05)
        self.ground.addSubview_(rv)

        num = k.label(str(i + 1), T1, pal["muted"])
        num.setAlignment_(AppKit.NSTextAlignmentRight)
        num.setFrame_(NSMakeRect(0, 7, 16, T1 + 6))
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
        if t["ok"]:
            attrs[AppKit.NSStrikethroughStyleAttributeName] = \
                AppKit.NSUnderlineStyleSingle
            attrs[AppKit.NSStrikethroughColorAttributeName] = pal["muted"]
        body = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            t["text"], attrs)

        tx = AppKit.NSTextField.alloc().initWithFrame_(
            NSMakeRect(24, 5, W - 16 - 24 - 56, 22))
        tx.setAttributedStringValue_(body)
        tx.setBackgroundColor_(AppKit.NSColor.clearColor())
        tx.setBezeled_(False)
        tx.setEditable_(False)
        tx.setSelectable_(False)
        tx.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        tx.setToolTip_(t["text"])
        rv.addSubview_(tx)

        x = self.button("✕", T1, pal["muted"], "kill:",
                        NSMakeRect(W - 16 - 56, 4, 24, 24))
        x.setTarget_(r)
        x.setToolTip_("删除")
        x.setHidden_(True)
        rv.addSubview_(x)
        rv.kill = x

        box = AppKit.NSButton.alloc().initWithFrame_(
            NSMakeRect(W - 16 - 28, 4, 24, 24))
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
            self.items.append({"text": text, "ok": False, "done_on": ""})
        if self.commit():
            self.render()
            self.focus()

    def toggle(self, i):
        if not (0 <= i < len(self.items)):
            return
        t = self.items[i]
        t["ok"] = not t["ok"]
        t["done_on"] = store.today() if t["ok"] else ""
        if self.commit():
            self.render()

    def remove(self, i):
        if not (0 <= i < len(self.items)):
            return
        self.items.pop(i)
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

    def controlTextDidChange_(self, note):
        """A single-line NSTextField flattens a multi-line paste into one
        string, so "five lines pasted" would have become one very long
        task. Catch it here instead: if what just landed has line breaks,
        it was a paste, and it is five tasks."""
        control = note.object()
        raw = control.stringValue()
        if "\n" in raw or "\r" in raw:
            control.setStringValue_("")
            self.w.add(raw)

    def control_textView_doCommandBySelector_(self, control, view, selector):
        name = selector.name() if hasattr(selector, "name") else str(selector)
        if name == "insertNewline:":
            text = control.stringValue()
            control.setStringValue_("")
            self.w.add(text)
            return True
        if name == "cancelOperation:":
            control.setStringValue_("")
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
