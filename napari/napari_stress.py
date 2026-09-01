"""Drive napari's threading machinery hard, from one process.

Three things happen at once:

* worker threads compute numpy results and hand them to the GUI thread by
  signal - that is napari's own thread_worker path;
* the same threads create, connect and drop QObjects, which is legal Qt
  (a QObject belongs to the thread that made it) and is what reaches the
  wrapper map, the parent/child graph and destruction from several threads;
* the GUI thread adds and removes layers underneath all of it.

Widgets stay on the GUI thread throughout.
"""
import os
import sys
import threading

import numpy as np
import napari
from napari.qt.threading import create_worker
from qtpy.QtCore import QObject, QTimer, Signal
from qtpy.QtWidgets import QApplication

WORKERS = int(os.environ.get("STRESS_WORKERS", "8"))
YIELDS = int(os.environ.get("STRESS_YIELDS", "60"))
CHURN = int(os.environ.get("STRESS_CHURN", "300"))
OBJ_THREADS = int(os.environ.get("STRESS_OBJ_THREADS", "6"))
OBJ_ITERS = int(os.environ.get("STRESS_OBJ_ITERS", "4000"))

rng = np.random.default_rng(0)


class Node(QObject):
    ping = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.seen = 0

    def on_ping(self, value):
        self.seen += value


def object_churn(stop):
    """Create, connect, parent and drop QObjects from a non-GUI thread."""
    n = 0
    while n < OBJ_ITERS and not stop.is_set():
        root = Node()
        kids = [Node(root) for _ in range(4)]
        for k in kids:
            k.ping.connect(root.on_ping)
        for k in kids:
            k.ping.emit(1)
        # Dropping the root takes the children with it.
        del kids
        del root
        n += 1
    return n


def compute(n):
    """Runs in a worker thread. Real work, no Qt."""
    for i in range(n):
        a = rng.random((128, 128))
        yield (a @ a.T).astype("float32")


def main():
    viewer = napari.Viewer(show=False, title="stress")
    state = {"received": 0, "churn": 0, "done": 0, "objects": 0}
    stop = threading.Event()

    def maybe_quit():
        if (state["done"] >= WORKERS and state["churn"] >= CHURN
                and not any(t.is_alive() for t in threads)):
            QTimer.singleShot(0, QApplication.instance().quit)

    def on_yield(data):
        state["received"] += 1
        if state["received"] % 5 == 0:
            viewer.add_image(data, name=f"w{state['received']}")
            if len(viewer.layers) > 4:
                viewer.layers.pop(0)

    def on_done():
        state["done"] += 1
        maybe_quit()

    workers = []
    for _ in range(WORKERS):
        w = create_worker(compute, YIELDS)
        w.yielded.connect(on_yield)
        w.finished.connect(on_done)
        workers.append(w)

    counts = {}

    def runner(idx):
        counts[idx] = object_churn(stop)

    threads = [threading.Thread(target=runner, args=(i,), daemon=True)
               for i in range(OBJ_THREADS)]

    def churn():
        if state["churn"] >= CHURN:
            maybe_quit()
            return
        state["churn"] += 1
        layer = viewer.add_points(rng.random((16, 2)) * 100,
                                  name=f"p{state['churn']}")
        viewer.layers.remove(layer)
        QTimer.singleShot(0, churn)

    for t in threads:
        t.start()
    for w in workers:
        w.start()
    QTimer.singleShot(0, churn)

    # Do not run forever if a thread wedges.
    QTimer.singleShot(120_000, lambda: (stop.set(),
                                        QApplication.instance().quit()))
    napari.run()

    stop.set()
    for t in threads:
        t.join(timeout=5)
    state["objects"] = sum(counts.values())

    print(f"gil={sys._is_gil_enabled()} yields={state['received']} "
          f"churn={state['churn']} finished={state['done']}/{WORKERS} "
          f"objects={state['objects']}")


if __name__ == "__main__":
    main()
