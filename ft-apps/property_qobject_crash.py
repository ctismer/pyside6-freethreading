# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
"""Reading back a QObject stored as a dynamic property segfaults.

    o = QObject()
    o.setProperty("p", QObject())
    o.property("p")                 # SIGSEGV

setProperty puts the QObject into the QVariant behind the dynamic property
table. Nothing keeps the Python wrapper alive past the statement, so it is
collected, the C++ object goes with it (Python owns what it created), and
the QVariant is left holding a dangling pointer. property() then converts
that pointer back to Python:

    getWrapperForQObject(QObject *, PyTypeObject *)    pyside.cpp:866
      QVariant existing = cppSelf->property(invalidatePropertyName);

and calls through a vtable that is not there any more - the crash lands on
address zero.

This has NOTHING to do with free threading. It was found by AddressSanitizer
while stress-testing dynamic properties from several threads, but it needs
neither threads nor a free-threaded build:

    PySide6 6.12.0a1, 3.15t, GIL off       segfault
    PySide6 6.12.0a1, 3.15t, PYTHON_GIL=1  segfault
    PySide6 6.12.0a1, CPython 3.14         segfault
    PySide6 6.11.2,   CPython 3.12         segfault   <- released wheel

Run it with any PySide6:

    python property_qobject_crash.py

Prints the two lines and dies on the third. A return code of 139 is the
finding.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject
import PySide6


def main() -> int:
    print(f"PySide6 {PySide6.__version__}, python {sys.version.split()[0]}",
          flush=True)
    holder = QObject()
    holder.setProperty("p", QObject())
    print("stored, reading it back now", flush=True)
    print("read back:", holder.property("p"), flush=True)
    print("survived - not reproduced on this build", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
