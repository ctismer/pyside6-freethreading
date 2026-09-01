"""Does the shape a Qt application actually uses scale?

Worker threads run Python-level work and hand each result to the GUI
thread through a Qt signal, which is what napari's thread_worker does.
The work is deliberately pure Python: numpy would release the GIL by
itself and the comparison would measure nothing.

Fixed total work, split over T threads. Run it once with PYTHON_GIL=1 and
once with PYTHON_GIL=0 and compare the columns.
"""
import os
import sys
import threading
import time

from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal

TOTAL = int(os.environ.get("TOTAL", "24"))       # work units overall
UNIT = int(os.environ.get("UNIT", "120000"))     # python loop per unit


class Emitter(QObject):
    produced = Signal(int)


class Sink(QObject):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.total = 0

    def on_produced(self, value):
        self.count += 1
        self.total += value


def unit_of_work(seed):
    """Pure Python. No C library that could release the GIL for us."""
    acc = seed
    for i in range(UNIT):
        acc = (acc * 1103515245 + 12345) & 0x7FFFFFFF
        if acc & 1:
            acc ^= i
    return acc


def worker(units, emitter):
    for u in range(units):
        value = unit_of_work(u)
        emitter.produced.emit(value)


def run(threads_count, sink):
    per = TOTAL // threads_count
    emitters = [Emitter() for _ in range(threads_count)]
    for e in emitters:
        e.produced.connect(sink.on_produced, Qt.QueuedConnection)
    ts = [threading.Thread(target=worker, args=(per, emitters[i]))
          for i in range(threads_count)]
    start = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return time.perf_counter() - start


def main():
    app = QCoreApplication(sys.argv)
    sink = Sink()

    print(f"gil={sys._is_gil_enabled()} total={TOTAL} unit={UNIT}")
    base = None
    for t in (1, 2, 4, 8):
        elapsed = run(t, sink)
        app.processEvents()
        if base is None:
            base = elapsed
        print(f"  threads={t:2}  {elapsed:6.2f}s  speedup {base / elapsed:5.2f}x")
    app.processEvents()
    print(f"  signals delivered to the GUI thread: {sink.count}")


if __name__ == "__main__":
    main()
