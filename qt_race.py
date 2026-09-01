"""Concurrency scenarios for the locks that replaced the coarse binding lock.

Each scenario hammers one of the places named in 5b97c99a5. Two of them
have no kill switch, so this is a regression guard rather than a proof:
it can show that the current code survives, and it would have caught the
unguarded connectionHash users that commit found.

  slot_registration   connect from many threads to one object - reaches
                      registerSlotConnection() and the dynamic meta object
  connect_disconnect  connect and disconnect the same signal while a third
                      thread emits - reaches disconnectSlot()
  shared_reader       many threads read from one object while another
                      drops it - reaches the call lease and the state lock,
                      which PYSIDE6_OPTION_FT=off can switch away
  shared_setter       the same, but mutating Qt state concurrently. That is
                      Qt misuse and is expected to fail; it marks where the
                      binding's protection ends

Run one scenario per process: a crash is a possible outcome.
"""
import os
import sys
import threading

from PySide6.QtCore import QObject, Signal

THREADS = int(os.environ.get("RACE_THREADS", "8"))
ITERS = int(os.environ.get("RACE_ITERS", "2000"))
SCENARIO = os.environ.get("RACE_SCENARIO", "slot_registration")


class Bus(QObject):
    sig = Signal(int)

    def __init__(self):
        super().__init__()
        self.hits = 0

    def slot(self, value):
        self.hits += value


def slot_registration():
    """Every thread adds its own slot to the same object."""
    bus = Bus()
    barrier = threading.Barrier(THREADS)

    def work(idx):
        barrier.wait()
        for i in range(ITERS):
            def handler(value, _i=i):
                pass
            bus.sig.connect(handler)
            bus.sig.disconnect(handler)

    run(work)
    return "survived"


def connect_disconnect():
    """Connect and disconnect under a concurrent emitter."""
    bus = Bus()
    stop = threading.Event()
    barrier = threading.Barrier(THREADS)

    def emitter():
        while not stop.is_set():
            bus.sig.emit(1)

    def work(idx):
        barrier.wait()
        for i in range(ITERS):
            bus.sig.connect(bus.slot)
            bus.sig.disconnect(bus.slot)

    e = threading.Thread(target=emitter, daemon=True)
    e.start()
    try:
        run(work)
    finally:
        stop.set()
        e.join(timeout=5)
    return "survived"


def shared_setter():
    """DELIBERATE Qt misuse: a setter on one shared QObject from N threads.

    QObject is not thread-safe for concurrent access to one instance, so
    this is expected to corrupt the heap. It is here to mark the boundary:
    the binding protects its own bookkeeping, not the object it wraps.
    With a GIL it survives by accident, because the GIL serialises the
    calls that Qt assumes are serialised anyway.
    """
    bus = Bus()
    barrier = threading.Barrier(THREADS)

    def work(idx):
        barrier.wait()
        for i in range(ITERS):
            bus.setObjectName(f"n{idx}-{i}")

    run(work)
    return "survived"


def shared_reader():
    """Legal use: read from many threads while the owner drops the object.

    No Qt state is mutated concurrently. What is exercised is the binding:
    the wrapper lookup, the call lease and destruction while calls are in
    flight. This one should stay clean.
    """
    box = {"obj": Bus()}
    barrier = threading.Barrier(THREADS)

    def work(idx):
        barrier.wait()
        for i in range(ITERS):
            obj = box.get("obj")
            if obj is not None:
                try:
                    obj.objectName()
                    obj.isWidgetType()
                except RuntimeError:
                    pass
            if idx == 0 and i % 100 == 0:
                box["obj"] = Bus()

    run(work)
    return "survived"


def run(work):
    ts = [threading.Thread(target=work, args=(i,)) for i in range(THREADS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


SCENARIOS = {
    "slot_registration": slot_registration,
    "connect_disconnect": connect_disconnect,
    "shared_setter": shared_setter,
    "shared_reader": shared_reader,
}

result = SCENARIOS[SCENARIO]()
print(f"{SCENARIO}: {result} gil={sys._is_gil_enabled()} "
      f"threads={THREADS} iters={ITERS} "
      f"option_ft={os.environ.get('PYSIDE6_OPTION_FT', '(default)')}")
