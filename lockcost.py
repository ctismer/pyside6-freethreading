"""Upper bound for the cost of one lock per binding call.

A per-object lock held across the C++ call is the shape that would make
concurrent access to one QObject memory-safe. This measures what such a
lock costs when uncontended, using a Python-level lock - which is slower
than the C++ mutex the real thing would use, so the answer is an upper
bound, not an estimate.
"""
import sys
import threading
import time

from PySide6.QtCore import QObject

N = 400000
obj = QObject()
lock = threading.Lock()


def timed(label, fn):
    fn(1000)
    start = time.perf_counter()
    fn(N)
    elapsed = time.perf_counter() - start
    per = elapsed / N * 1e9
    print(f"  {label:34} {elapsed:6.3f}s   {per:7.1f} ns/call")
    return per


def bare(n):
    for _ in range(n):
        obj.objectName()


def locked(n):
    for _ in range(n):
        with lock:
            obj.objectName()


def lock_only(n):
    for _ in range(n):
        with lock:
            pass


print(f"gil={sys._is_gil_enabled()} calls={N}")
a = timed("obj.objectName()", bare)
b = timed("with lock: obj.objectName()", locked)
c = timed("with lock: pass", lock_only)
print(f"\n  lock overhead on top of the call: {b - a:.1f} ns "
      f"({(b - a) / a * 100:.0f}% of the call)")
print(f"  a bare python lock alone costs   : {c:.1f} ns")
