# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
"""Does __feature__ survive threads creating types at the same time?

ThreadSanitizer flagged sbkfeature_base.cpp:72 in five of the eight A/B
scenarios. The variable is one plain global:

    static SelectableFeatureHook SelectFeatureSet = nullptr;

    SelectableFeatureHook initSelectableFeature(SelectableFeatureHook func)
    {
        auto ret = SelectFeatureSet;
        SelectFeatureSet = func;
        ...
    }

and it is used as save-and-restore around type creation, twice - in
_setupNew() and in sbkmodule.cpp - to keep feature switching out of the
creation process (PYSIDE-1463). Two of those pairs from two threads lose
the value:

    T1: save = hook;     SelectFeatureSet = nullptr
    T2: save = nullptr;  SelectFeatureSet = nullptr    <- saves the wrong one
    T1:                  SelectFeatureSet = hook
    T2:                  SelectFeatureSet = nullptr    <- stays off

Nothing crashes. snake_case simply stops working, in a process that had
it a moment ago.

This asks whether that happens. One thread checks a renamed method over
and over while the others create QObject subclasses, which is what runs
the save-and-restore. Every check that comes back camelCase-only while
the feature is on is a lost race.

    python feature_race.py [seconds]

Prints one line per run. On a build with a GIL it must never report a
loss; that is the control, and it is why the script runs the same way on
both.
"""
from __future__ import annotations

import sys
import threading
import time

from PySide6.QtCore import QObject

STOP = threading.Event()
losses = []
checks = [0]


def make_types(n: int) -> None:
    """Create subclasses, which is what takes the save-and-restore path."""
    while not STOP.is_set():
        for i in range(20):
            type(f"Sub{n}_{i}", (QObject,), {})


def check_feature() -> None:
    """Ask an object whether the feature is still in effect.

    setObjectName is the camelCase name; with snake_case switched on the
    attribute is set_object_name, and the camelCase one is gone. Seeing
    the camelCase name means the switch is no longer in effect.
    """
    from __feature__ import snake_case  # noqa: F401

    while not STOP.is_set():
        obj = QObject()
        checks[0] += 1
        if not hasattr(obj, "set_object_name"):
            losses.append(("no snake_case", checks[0]))
        del obj


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    gil = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True

    threads = [threading.Thread(target=make_types, args=(n,)) for n in range(4)]
    threads.append(threading.Thread(target=check_feature))
    for t in threads:
        t.start()
    time.sleep(seconds)
    STOP.set()
    for t in threads:
        t.join()

    state = "GIL on " if gil else "GIL off"
    print(f"{state}  checks {checks[0]:6d}  lost {len(losses)}")
    return 1 if losses else 0


if __name__ == "__main__":
    sys.exit(main())
