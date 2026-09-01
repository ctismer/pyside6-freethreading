"""Does the stripe table's layout matter?

The guard picks its mutex as (address >> 4) & (stripes - 1). PyMutex is one
byte, so an unpadded table of them puts 64 stripes on a single cache line.
Two threads locking unrelated objects then still fight over that line.

To make it visible the objects cannot be left to chance. Their C++
addresses are read out and sorted into two groups:

  same     every object's stripe lands in one 64-entry block, so unpadded
           they share one cache line - the worst case, constructed
  apart    the stripes are at least 64 apart, so they never do - the best
           case, equally constructed
  natural  the objects as the allocator handed them out, unselected

Only the third one decides anything. The other two bracket it: they say
how much room there is between the best and worst layout, so it is clear
whether the natural case sits near one of them or in between. Objects a
GUI creates in a row have nearby addresses, and 64 neighbouring stripes
are one cache line, so the natural case may well be the bad one.

Same work, same number of lock operations, only the addresses differ. Run
with the state lock switched off (PYSIDE6_OPTION_FT=0b101), or its single
global mutex hides everything this is trying to show.
"""
import os
import sys
import threading
import time

from PySide6.QtCore import QObject
import shiboken6

THREADS = int(os.environ.get("FS_THREADS", "8"))
ITERS = int(os.environ.get("FS_ITERS", "200000"))
POOL = int(os.environ.get("FS_POOL", "20000"))
STRIPES = int(os.environ.get("PYSIDE6_FT_CALLGUARD_STRIPES", "1024"))
PER_LINE = 64  # PyMutex is one byte, a cache line is 64 of them


def stripe_of(obj):
    address = shiboken6.getCppPointer(obj)[0]
    return (address >> 4) & (STRIPES - 1)


def pick_groups():
    """Return (same_line, different_lines), THREADS objects each."""
    pool = [QObject() for _ in range(POOL)]
    by_line = {}
    by_stripe = {}
    for o in pool:
        s = stripe_of(o)
        by_line.setdefault(s // PER_LINE, []).append(o)
        by_stripe.setdefault(s, o)

    same = None
    for line, objs in by_line.items():
        # Distinct stripes inside one line, so the locks differ but the
        # cache line does not.
        distinct = {stripe_of(o): o for o in objs}
        if len(distinct) >= THREADS:
            same = list(distinct.values())[:THREADS]
            break

    apart = []
    for line in sorted(by_line):
        if len(apart) == THREADS:
            break
        apart.append(by_line[line][0])

    natural = pool[:THREADS]
    return same, apart[:THREADS], natural, pool


def hammer(obj, n):
    for _ in range(n):
        obj.objectName()
        obj.isWidgetType()


def run(objs):
    ts = [threading.Thread(target=hammer, args=(objs[i], ITERS))
          for i in range(len(objs))]
    start = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return time.perf_counter() - start


same, apart, natural, _pool = pick_groups()
# With a single stripe there are no distinct ones to sort into groups, and
# the constructed groups are meaningless anyway - only the natural one is
# measured then.
coarse = STRIPES == 1 or same is None or len(apart) < THREADS

print(f"gil={sys._is_gil_enabled()} threads={THREADS} iters={ITERS} "
      f"stripes={STRIPES} "
      f"padded={os.environ.get('PYSIDE6_FT_CALLGUARD_PADDED', '(default)')} "
      f"option_ft={os.environ.get('PYSIDE6_OPTION_FT', '(default)')}")
if not coarse:
    print(f"  stripes same line : {sorted(stripe_of(o) for o in same)}")
    print(f"  stripes apart     : {sorted(stripe_of(o) for o in apart)}")
print(f"  stripes natural   : {sorted(stripe_of(o) for o in natural)}")
print(f"  natural lines     : "
      f"{sorted({stripe_of(o) // PER_LINE for o in natural})}")
# Interleaved, because running one group three times and then the next
# measures the machine warming up as much as the layout. Five rounds,
# median reported: the minimum rewards a lucky round, the mean a bad one.
import statistics

groups = ((("natural", natural),) if coarse
          else (("same cache line", same), ("different lines", apart),
                ("natural", natural)))
samples = {label: [] for label, _ in groups}
for _round in range(5):
    for label, objs in groups:
        samples[label].append(run(objs))
for label, _ in groups:
    values = sorted(samples[label])
    print(f"  {label:16} median {statistics.median(values):6.3f}s   "
          f"range {values[0]:.3f}-{values[-1]:.3f}")
