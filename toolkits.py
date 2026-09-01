"""The same parallel workload, handed to the GUI thread three ways.

  none     - results go into a list; the floor, no toolkit involved
  tkinter  - queue plus after(), the documented way to reach Tk safely
  pyside   - queued signal, the documented way to reach Qt safely

Fixed total work over T threads. The interesting number is the speedup,
not the absolute time: it says how much of the parallel gain survives the
handover a real application has to perform.
"""
import os
import sys
import threading
import time

TOTAL = int(os.environ.get("TOTAL", "24"))
UNIT = int(os.environ.get("UNIT", "120000"))
KIND = os.environ.get("KIND", "none")


def unit_of_work(seed):
    acc = seed
    for i in range(UNIT):
        acc = (acc * 1103515245 + 12345) & 0x7FFFFFFF
        if acc & 1:
            acc ^= i
    return acc


def bench(make_sink, threads_count):
    """make_sink() returns (emit_callable, drain_callable)."""
    emit, drain = make_sink(threads_count)

    def worker(units, idx):
        for u in range(units):
            emit(idx, unit_of_work(u))

    per = TOTAL // threads_count
    ts = [threading.Thread(target=worker, args=(per, i))
          for i in range(threads_count)]
    start = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    elapsed = time.perf_counter() - start
    drain()
    return elapsed


def sink_none(n):
    got = []
    return (lambda i, v: got.append(v)), (lambda: None)


def sink_tk(n):
    import queue
    import tkinter as tk
    q = queue.Queue()
    root = tk.Tk()
    root.withdraw()
    seen = []

    def poll():
        while True:
            try:
                seen.append(q.get_nowait())
            except queue.Empty:
                break

    def drain():
        poll()
        root.update()
        root.destroy()

    return (lambda i, v: q.put(v)), drain


def sink_pyside(n):
    from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    class Emitter(QObject):
        produced = Signal(int)

    class Sink(QObject):
        def __init__(self):
            super().__init__()
            self.count = 0

        def on_produced(self, value):
            self.count += 1

    sink = Sink()
    emitters = [Emitter() for _ in range(n)]
    for e in emitters:
        e.produced.connect(sink.on_produced, Qt.QueuedConnection)

    def drain():
        app.processEvents()

    return (lambda i, v: emitters[i].produced.emit(v)), drain


SINKS = {"none": sink_none, "tkinter": sink_tk, "pyside": sink_pyside}

print(f"kind={KIND} gil={sys._is_gil_enabled()} total={TOTAL} unit={UNIT}")
base = None
for t in (1, 2, 4, 8):
    elapsed = bench(SINKS[KIND], t)
    if base is None:
        base = elapsed
    print(f"  threads={t:2}  {elapsed:6.2f}s  speedup {base / elapsed:5.2f}x")
