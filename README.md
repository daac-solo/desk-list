# 桌面清单 · Desk List

A task list that lives on the macOS desktop. Type a line, press Return.
Click the circle when it's done — the task doesn't disappear, it gets a
line drawn through it and stays.

<!-- screenshot -->

## Why it finishes tasks instead of deleting them

Most lists treat "done" as "gone". That's efficient and it's also the
reason the list always looks like work you haven't done. A crossed-out
line is the only record that the day went anywhere.

So: finished tasks keep their number and their place. `清掉已完成` removes
them when you actually want them gone.

## What it does

| | |
|---|---|
| `⏎` | one line, one task |
| paste several lines | several tasks, not one long one |
| click the circle | done — a line draws through the text |
| hover a row | `✕` to delete it |
| `∧` | collapse to the title bar |
| `⌃⌘L` | show / hide |
| drag anywhere | move it; it comes back there next launch |

Tasks are in `~/.local/share/desk-list/tasks.json` — plain JSON, yours to
read, edit, or sync. Nothing leaves the machine.

## Install

```sh
git clone https://github.com/daac-solo/desk-list
cd desk-list
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python desklist.py          # run it
./.venv/bin/python setup.py py2app      # or build Desk List.app
```

`⌃⌘L` needs Accessibility permission (System Settings → Privacy &
Security → Accessibility). Everything else works without it. Permission is
granted to a binary, so after rebuilding the app you may have to remove
and re-add it rather than just re-ticking the box.

## Design

Colours, radius and the three type sizes come from
[`mac-desk-kit`](https://github.com/daac-solo/mac-desk-kit), which reads
one palette file shared across my tools. Three font sizes on a screen,
counted not estimated; contrast measured in both light and dark, never
eyeballed.

The one measurement worth repeating: the unfinished circle uses the
secondary text colour, not the divider colour. The divider token came out
at **1.42:1** against the glass, and this is the single thing on the
widget you are meant to click. A button too faint to see is the same as no
button.

## Not in here

No sync, no due dates, no projects, no notifications. Those are a
different app. This one is a sheet of paper you can't lose.

## License

MIT
