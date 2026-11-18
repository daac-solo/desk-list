"""
Global hotkeys via NSEvent's global monitor.

Carbon's RegisterEventHotKey would avoid the Accessibility prompt, but its
handler never fires inside this rumps/PyObjC runloop — registration reports
success and the event is never delivered. The NSEvent monitor is the path
that actually works here; the cost is a one-time permission grant.
"""

import AppKit

# ApplicationServices is not pulled into the app bundle, so reach the same
# symbol through whichever framework is actually present.
AXIsProcessTrusted = None
for _mod in ("ApplicationServices", "Quartz", "HIServices"):
    try:
        AXIsProcessTrusted = __import__(_mod, fromlist=["AXIsProcessTrusted"]).AXIsProcessTrusted
        break
    except Exception:
        continue

CMD = AppKit.NSEventModifierFlagCommand
SHIFT = AppKit.NSEventModifierFlagShift
OPT = AppKit.NSEventModifierFlagOption
CTRL = AppKit.NSEventModifierFlagControl

_RELEVANT = CMD | SHIFT | OPT | CTRL

KEYS = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "o": 31, "u": 32, "i": 34, "p": 35, "l": 37,
    "j": 38, "k": 40, "n": 45, "m": 46,
}


def trusted():
    """Whether Accessibility is granted. Without it the monitor installs
    silently and never fires, which looks exactly like a broken hotkey."""
    if AXIsProcessTrusted is None:
        return False
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


class HotKeys:
    def __init__(self):
        self._binds = {}      # (keycode, mods) -> callback
        self._monitor = None
        self._local = None

    def register(self, key, mods, callback):
        code = KEYS.get(key.lower())
        if code is None:
            return False
        self._binds[(code, mods)] = callback
        self._install()
        return True

    def _install(self):
        if self._monitor is not None:
            return

        def handle(event):
            try:
                mods = event.modifierFlags() & _RELEVANT
                cb = self._binds.get((event.keyCode(), mods))
                if cb:
                    cb()
            except Exception:
                import traceback
                traceback.print_exc()

        mask = AppKit.NSEventMaskKeyDown
        self._monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            mask, handle)

        # The global monitor does not see our own windows, so the keys would
        # stop working the moment the panel itself had focus.
        def handle_local(event):
            handle(event)
            return event

        self._local = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, handle_local)
