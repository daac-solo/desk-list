"""Where the tasks live.

A list you write things into has exactly one thing it must never do, and
that is lose them. So every write is atomic and every write returns
whether it worked — a save that failed silently and a save that worked
look identical from the outside, and that is the bug this whole codebase
keeps shipping.
"""

import io
import json
import os
from datetime import date

FILE = os.path.join(os.path.expanduser("~"),
                    ".local", "share", "desk-list", "tasks.json")


def load():
    try:
        with io.open(FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        items = d.get("items", []) if isinstance(d, dict) else d
        out = []
        for it in items:
            if isinstance(it, dict) and str(it.get("text", "")).strip():
                out.append({"text": str(it["text"]),
                            "ok": bool(it.get("ok")),
                            "done_on": it.get("done_on") or ""})
        return out
    except FileNotFoundError:
        return []
    except Exception as e:
        # Do not start empty on a parse error — that reads as "you had no
        # tasks" and the next save overwrites the file you could have
        # recovered. Move it aside and say so.
        print("desk-list: tasks.json unreadable (%s)" % type(e).__name__, flush=True)
        try:
            os.replace(FILE, FILE + ".broken")
            print("desk-list: kept the old file at tasks.json.broken", flush=True)
        except Exception:
            pass
        return []


def save(items):
    """True when it is on disk. Callers must look."""
    try:
        os.makedirs(os.path.dirname(FILE), exist_ok=True)
        tmp = FILE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"v": 1, "items": items}, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, FILE)
        return True
    except Exception as e:
        print("desk-list: NOT saved (%s: %s)" % (type(e).__name__, e), flush=True)
        return False


def split(raw):
    """One line, one task. Pasting five lines should give five tasks, not
    one very long one."""
    return [s.strip() for s in str(raw).replace("\r", "\n").split("\n") if s.strip()]


def today():
    return date.today().isoformat()
