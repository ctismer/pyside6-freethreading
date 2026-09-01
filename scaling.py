"""How far does a given workload scale across threads?

Fixed total work, split over T threads. Perfect scaling halves the wall
time when T doubles; a serialising lock keeps it flat.

Two workloads:
  qobject  - create, connect and destroy QObjects. Almost pure binding
             bookkeeping, which is what the state lock serialises.
  numpy    - matrix work with no binding involved, as the control.
"""
import os
import sys
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal

TOTAL = int(os.environ.get("TOTAL", "40000"))
WORKLOAD = os.environ.get("WORKLOAD", "qobject")


class Node(QObject):
    ping = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.seen = 0

    def on_ping(self, value):
        self.seen += value


def qobject_work(n):
    for _ in range(n):
        root = Node()
        kids = [Node(root) for _ in range(4)]
        for k in kids:
            k.ping.connect(root.on_ping)
        for k in kids:
            k.ping.emit(1)
        del kids
        del root


def numpy_work(n):
    rng = np.random.default_rng()
    reps = max(1, n // 200)
    for _ in range(reps):
        a = rng.random((128, 128))
        (a @ a.T).sum()


def plain_work(n):
    """Plain QObjects: no Python subclass, so no dynamic meta object."""
    for _ in range(n):
        root = QObject()
        kids = [QObject(root) for _ in range(4)]
        del kids
        del root


def subclass_work(n):
    """Python subclass, but no signal traffic - only construction."""
    for _ in range(n):
        root = Node()
        kids = [Node(root) for _ in range(4)]
        del kids
        del root


class PyNode:
    __slots__ = ("parent", "kids", "seen")

    def __init__(self, parent=None):
        self.parent = parent
        self.kids = []
        self.seen = 0
        if parent is not None:
            parent.kids.append(self)


def pyobj_work(n):
    """Same shape in pure Python: rules out the allocator as the cause."""
    for _ in range(n):
        root = PyNode()
        kids = [PyNode(root) for _ in range(4)]
        del kids
        del root


# Pre-created, one per thread: no wrapper churn, so this isolates the call
# guard's granularity from the binding manager's map.
_call_objects = [QObject() for _ in range(64)]
_next_object = [0]
_object_lock = threading.Lock()


def callmany_work(n):
    with _object_lock:
        mine = _call_objects[_next_object[0] % len(_call_objects)]
        _next_object[0] += 1
    for _ in range(n):
        mine.objectName()
        mine.isWidgetType()


WORK = {"callmany": callmany_work, "pyobj": pyobj_work, "qobject": qobject_work, "numpy": numpy_work,
        "plain": plain_work, "subclass": subclass_work}[WORKLOAD]

print(f"workload={WORKLOAD} total={TOTAL} gil={sys._is_gil_enabled()} "
      f"option_ft={os.environ.get('PYSIDE6_OPTION_FT', '(default)')}")

base = None
for t in (1, 2, 4, 8, 16):
    per = TOTAL // t
    threads = [threading.Thread(target=WORK, args=(per,)) for _ in range(t)]
    start = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    elapsed = time.perf_counter() - start
    if base is None:
        base = elapsed
    print(f"  threads={t:3}  {elapsed:7.2f}s  speedup {base / elapsed:5.2f}x")
