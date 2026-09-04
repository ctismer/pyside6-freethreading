"""Does Shiboken.delete(parent) leave a child usable that the GIL build keeps?

markOwnedSetPendingLocked() sets the one-way pendingDestruction flag on the
whole graph below the root, without the "only if it is not a wrapper class"
rule that collectInvalidateLocked() applies. If the two sets differ in a way a
caller can see, a free-threaded build refuses a child that a build with a GIL
still answers for. Run under both interpreters and diff the output.
"""
import sys

from PySide6.QtCore import QObject
from shiboken6 import Shiboken


class Sub(QObject):
    """A Python subclass: its C++ side is a generated wrapper, so
    collectInvalidateLocked() leaves validCppObject alone for it."""


def case(name, make):
    parent = QObject()
    child = make(parent)
    before = Shiboken.isValid(child)
    Shiboken.delete(parent)
    after = Shiboken.isValid(child)
    called = None
    try:
        child.objectName()
        called = "ok"
    except RuntimeError as e:
        called = f"RuntimeError: {str(e)[:48]}"
    print(f"{name:<22} valid before={before!s:<5} after={after!s:<5} call={called}")


print(f"python: {sys.version.split()[0]}  "
      f"free-threaded={not getattr(sys, '_is_gil_enabled', lambda: True)()}")

case("plain child", lambda p: QObject(p))
case("subclass child", lambda p: Sub(p))
case("detached before", lambda p: (lambda c: (c.setParent(None), c)[1])(QObject(p)))
