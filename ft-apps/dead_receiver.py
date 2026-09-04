"""Emit a signal into a bound method whose receiver is dying.

MethodDynamicSlot keeps the receiver as a raw, unowned PyObject* and
rebuilds the bound method on every call:

    PepExt_Type_CallDescrGet(m_function, m_pythonSelf, nullptr)

Nothing there checks whether m_pythonSelf is still alive. The weakref that
fires on the receiver's death is what disconnects - and in a build with the
GIL that callback runs disconnectReceiver() inside Py_BEGIN_ALLOW_THREADS,
so the GIL is free while the receiver is already dying and the connection
still stands.

This drives that window: one thread creates receivers and drops them, the
other emits. A receiver that is called after its death shows up as an
AttributeError on an attribute its __init__ always sets.
"""
import os
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal, Qt

ROUNDS = int(os.environ.get("ROUNDS", "20000"))
EMITTERS = int(os.environ.get("EMITTERS", "3"))

late_calls = []
live_calls = 0
stop = threading.Event()


class Sender(QObject):
    fired = Signal(int)


class Receiver:
    """Every instance has `marker` from the moment it exists."""

    def __init__(self, sender):
        self.marker = "alive"
        sender.fired.connect(self.on_fired, Qt.ConnectionType.DirectConnection)

    def on_fired(self, value):
        global live_calls
        try:
            self.marker
        except AttributeError as exc:
            late_calls.append(f"{exc}")
            stop.set()
        else:
            live_calls += 1


sender = Sender()


def churn():
    """Create receivers and drop them, so their weakrefs keep firing."""
    while not stop.is_set():
        r = Receiver(sender)
        del r


def emitter():
    for i in range(ROUNDS):
        if stop.is_set():
            return
        sender.fired.emit(i)


def main():
    print("python", sys.version.split()[0],
          "PySide6", __import__("PySide6.QtCore", fromlist=["x"]).__version__,
          "gil", getattr(sys, "_is_gil_enabled", lambda: True)())
    churner = threading.Thread(target=churn, daemon=True)
    churner.start()
    threads = [threading.Thread(target=emitter) for _ in range(EMITTERS)]
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    elapsed = time.perf_counter() - started
    if late_calls:
        print(f"CALLED AFTER DEATH: {len(late_calls)} times, e.g. {late_calls[0]}")
    else:
        print(f"no late call in {ROUNDS} x {EMITTERS} emits ({elapsed:.1f}s), "
              f"{live_calls} slot invocations reached a live receiver")


if __name__ == "__main__":
    main()
