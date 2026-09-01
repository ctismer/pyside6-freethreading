# Results

The output of the scripts in this repository, so that the numbers can be
read without building anything. Produced on 2026-09-01, all in one sitting
on one machine.

```
python 3.14.3 free-threading
PySide6 6.12.0 (6.12.0a1 preview wheels)   Qt 6.12.0
arm64, macOS 14.7, 10 cores (8 performance + 2 efficiency)
```

Every measurement that compares "with the GIL" against "without" runs the
same interpreter and the same wheels twice, switched by `PYTHON_GIL`. The
lock experiments switch our own locks off with `PYSIDE6_OPTION_FT` in the
same binary, so no rebuild sits between the two columns.

## napari's Qt test suite

The point is not that it passes. It is that both columns agree.

| | tests | passed | failed | errors | skipped |
|---|---|---|---|---|---|
| `PYTHON_GIL=1` | 984 | 906 | 12 | 2 | 64 |
| `PYTHON_GIL=0` | 984 | 906 | 12 | 2 | 64 |

The same twelve tests fail in both columns, so they are the environment and
not free threading: eight are `DID NOT WARN` under pytest 9 where napari
asks for >= 8.3.5, the rest are a screenshot test on a zero-size window and
its neighbours.

## Which packages re-enable the GIL

`gilscan.py` imports every top-level package in the environment in its own
process, because the flag is process-wide and never goes back.

```
probed 73 top-level packages

bermuda:
    The global interpreter lock (GIL) has been enabled to load module
    'bermuda._bermuda', which has not declared that it can run safely
    without the GIL.
```

One offender out of 73. Two more are known that this scan cannot see,
because they are not top-level packages:

- `vispy.visuals.text._sdf_cpu` — no free-threading declaration, and napari
  reaches it as soon as it draws text. A pure numerical routine (an 8SSEDT
  distance transform); it looks safe, it just does not say so. Cython 3.1
  needs one line, `freethreading_compatible=True`.
- `numcodecs` — no free-threaded wheel at all, which takes `zarr` with it.

`PYTHON_GIL=0` overrides all three meanwhile. Everything else in the napari
stack was fine: numpy, scipy, pandas, scikit-image, aiohttp, rapidfuzz,
napari-metadata.

## Does the shape a Qt application uses scale?

`parallel.py` — worker threads doing Python-level work, each result handed
to the GUI thread by queued signal. The work is deliberately pure Python;
numpy would release the GIL by itself and the comparison would measure
nothing.

```
### PYTHON_GIL=1
gil=True total=24 unit=120000
  threads= 1    0.41s  speedup  1.00x
  threads= 2    0.41s  speedup  0.99x
  threads= 4    0.41s  speedup  0.99x
  threads= 8    0.41s  speedup  1.00x
  signals delivered to the GUI thread: 96

### PYTHON_GIL=0
gil=False total=24 unit=120000
  threads= 1    0.42s  speedup  1.00x
  threads= 2    0.22s  speedup  1.86x
  threads= 4    0.13s  speedup  3.15x
  threads= 8    0.08s  speedup  5.26x
  signals delivered to the GUI thread: 96
```

## What the handover to the GUI thread costs

`toolkits.py` — the same load, handed to the GUI thread three ways: not at
all, through tkinter's `queue` plus `after()`, and through a queued Qt
signal.

```
### KIND=none  PYTHON_GIL=0        ### KIND=tkinter        ### KIND=pyside
  threads= 1    0.41s  1.00x         0.41s  1.00x            0.41s  1.00x
  threads= 2    0.22s  1.88x         0.22s  1.90x            0.24s  1.74x
  threads= 4    0.13s  3.12x         0.14s  2.92x            0.13s  3.11x
  threads= 8    0.08s  5.20x         0.06s  7.22x            0.07s  5.57x
```

All three land in one band. The handover is not what limits this.

## Qt objects themselves do not scale, by design

`scaling.py` with the `qobject` workload creates, connects and destroys
QObjects - almost pure binding work, and exactly what our locks serialize.

```
### PYTHON_GIL=1                    ### PYTHON_GIL=0
  threads=  1     1.76s  1.00x        1.70s  1.00x
  threads=  2     2.21s  0.80x        1.56s  1.09x
  threads=  4     3.07s  0.57x        1.89s  0.90x
  threads=  8     5.51s  0.32x        2.93s  0.58x
  threads= 16     5.94s  0.30x        3.19s  0.53x
```

Neither column scales, and that is the intended outcome: Qt is not
thread-safe per object, so the binding serializes what reaches one object.
What free threading buys an application is the *other* work - the Python
and numpy that runs beside the GUI, which is what `parallel.py` measures.
Free threading still wins here in absolute terms, roughly a factor of two
at eight threads, because the GIL column pays for contention on top.

## What the per-object guard costs

`callcost.py` - one guarded call, single-threaded and uncontended:

```
guard on  : 300000 calls in 0.093s = 311 ns/call
guard off : 300000 calls in 0.091s = 304 ns/call
```

About 7 ns, or 2%. `lockcost.py` puts an upper bound on it from the Python
side, by wrapping the same call in a Python lock:

```
  obj.objectName()                    0.093s     232.0 ns/call
  with lock: obj.objectName()         0.133s     332.8 ns/call
  with lock: pass                     0.040s     100.2 ns/call
```

A lock taken in Python costs 100 ns. The guard in C++ costs 7. That gap is
the reason it sits where it sits.

## Does the stripe table's layout matter?

`falsesharing.py` - the guard picks its mutex as `(address >> 4) & (stripes
- 1)`. `PyMutex` is one byte, so 64 of them share a cache line and two
threads locking unrelated objects could still fight over it. The script
forces objects into stripes that share a line and into stripes that do not.

```
gil=False threads=8 iters=200000 stripes=1024
  same cache line  median  1.880s   range 1.843-1.892
  different lines  median  1.861s   range 1.845-1.884
  natural          median  1.903s   range 1.878-1.922
```

Within 2%, and the ranges overlap. Padding the table to a cache line each
would cost 64 KB and buy nothing measurable, so the table stays unpadded.

## The locks earn their place

`qt_race.py` runs four concurrency scenarios, eight threads, 2000
iterations. With every lock in place:

```
slot_registration  : survived
connect_disconnect : survived
shared_reader      : survived
shared_setter      : survived
```

`shared_setter` calls a Qt setter on one object from eight threads - the
case Qt does not allow and the guard exists for. Same binary, guard
switched off, five runs each:

```
guard on  (PYSIDE6_OPTION_FT unset)   : 5 runs, 5 clean
guard off (PYSIDE6_OPTION_FT=0b011)   : 5 runs, 5 SIGABRT
```

That is what the kill switches are for. A lock that can never be removed
proves nothing; this one can be removed, and the scenario then dies every
time.
