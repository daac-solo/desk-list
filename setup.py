"""Build Desk List.app.

    ./.venv/bin/python setup.py py2app
"""

import os
import sys

from setuptools import setup

# deskkit lives in its own repo so 桌面清单 and 瞭望鸡 cannot drift apart
# again. An editable install points at it through a .pth file, and
# modulegraph does not follow those — the build then succeeds, ships
# without deskkit, and the app dies on launch with ModuleNotFoundError.
# Putting the real directory on sys.path is what makes the bundle contain
# the module instead of a promise of it.
KIT = os.path.expanduser("~/tools/mac-desk-kit")
if os.path.isdir(KIT):
    sys.path.insert(0, KIT)

setup(
    app=["desklist.py"],
    data_files=[],
    options={
        "py2app": {
            "argv_emulation": False,
            "plist": {
                "CFBundleName": "Desk List",
                "CFBundleDisplayName": "桌面清单",
                "CFBundleIdentifier": "com.daac.desklist",
                "CFBundleShortVersionString": "1.0",
                "CFBundleVersion": "1.0",
                # Accessory: no Dock icon, no menu of its own. It is a
                # widget, not an application you switch to.
                "LSUIElement": True,
                "NSHumanReadableCopyright": "MIT",
            },
            # Imported inside try blocks and through sys.path, neither of
            # which modulegraph follows. Without naming them the built app
            # starts and then quietly has no hotkey and no palette.
            "includes": ["tasks", "hotkeys", "deskkit"],
            "packages": ["rumps"],
        }
    },
    setup_requires=["py2app"],
)
