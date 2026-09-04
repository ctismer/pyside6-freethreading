# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
"""Does a wrapper lose attributes when two threads first touch its dict?

ThreadSanitizer flagged basewrapper.cpp:175 during the pyside6 suite under
TSan:

    LIBSHIBOKEN_API PyObject *SbkObject_GetDict_NoRef(PyObject *op)
    {
        auto *sbkObj = reinterpret_cast<SbkObject *>(op);
        if (!sbkObj->ob_dict) {                 // both threads see nullptr
            Shiboken::GilState state;
            sbkObj->ob_dict = PyDict_New();     // both create, one wins
        }
        return sbkObj->ob_dict;
    }

Check-then-act on a plain PyObject * field. The loser of the race gets a
dictionary that is no longer the object's own, so an attribute set through
it is written to a dictionary nobody will read again - it does not raise,
it just is not there afterwards.

The caller in the report is Sbk_GetPyOverride, which asks the instance
dictionary whether a virtual method has been overridden in Python. It takes
a virtual call to reach the racing branch - a plain setattr goes through
tp_dictoffset and never gets there. So the scenario does both at once on
the same fresh wrapper: half the threads trigger a virtual call, the other
half set an attribute, and every attribute is read back afterwards. A
wrapper that ends up with two dictionaries loses whatever was written to
the one that lost.

    python dict_race.py [rounds]

Prints one line. With a GIL there must never be a loss; that is the
control, and it is why the script runs the same way on both.
"""
from __future__ import annotations

import sys
import threading

from PySide6.QtCore import QObject

THREADS = 8


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    gil = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True

    lost = 0
    checked = 0
    for _ in range(rounds):
        # A fresh subclass and instance per round, so ob_dict is still
        # nullptr and the first touch from every thread takes the branch
        # that creates it. The override is what makes Sbk_GetPyOverride
        # look into the instance dictionary at all.
        cls = type("W", (QObject,), {"eventFilter": lambda self, o, e: False})
        obj = cls()
        watched = QObject()
        barrier = threading.Barrier(THREADS)

        def worker(idx: int) -> None:
            barrier.wait()
            if idx % 2:
                # Sbk_GetPyOverride -> SbkObject_GetDict_NoRef
                watched.installEventFilter(obj)
                watched.removeEventFilter(obj)
            else:
                setattr(obj, f"a{idx}", idx)

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(THREADS)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

        for i in range(0, THREADS, 2):
            checked += 1
            if getattr(obj, f"a{i}", None) != i:
                lost += 1

    state = "GIL on " if gil else "GIL off"
    print(f"{state}  rounds {rounds}  attributes {checked}  lost {lost}")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
