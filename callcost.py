"""What one guarded call costs, single-threaded and uncontended.

The suite is single-threaded, so any slowdown there is per-call overhead,
not contention. This measures it directly.
"""
import os
import sys
import time

from PySide6.QtCore import QObject

N = int(os.environ.get("N", "300000"))

OBJECTS = int(os.environ.get("OBJECTS", "1"))

objs = [QObject() for _ in range(OBJECTS)]
for o in objs:
    o.setObjectName("x")

# warm up
for _ in range(1000):
    objs[0].objectName()

start = time.perf_counter()
for i in range(N):
    objs[i % OBJECTS].objectName()
elapsed = time.perf_counter() - start

print(f"objects={OBJECTS} option_ft={os.environ.get('PYSIDE6_OPTION_FT', '(default)')} "
      f"gil={sys._is_gil_enabled()} "
      f"{N} calls in {elapsed:.3f}s = {elapsed / N * 1e9:.0f} ns/call")
