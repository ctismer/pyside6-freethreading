# Results

The output of the scripts in this repository, so the numbers can be read
without building anything. All produced on 2026-09-01, one machine, one
sitting.

```
python 3.14.3 free-threading
PySide6 6.12.0 (6.12.0a1 preview wheels)   Qt 6.12.0
arm64, macOS 14.7, 10 cores (8 performance + 2 efficiency)
```

Each comparison runs the same interpreter and the same wheels twice,
switched by `PYTHON_GIL`. The lock experiments switch our own locks off
with `PYSIDE6_OPTION_FT` in the same binary; no rebuild sits between the
columns.

## napari's Qt suite — both columns agree

| | tests | passed | failed | errors | skipped |
|---|---|---|---|---|---|
| `PYTHON_GIL=1` | 984 | 906 | 12 | 2 | 64 |
| `PYTHON_GIL=0` | 984 | 906 | 12 | 2 | 64 |

The same twelve fail in both, so they are the environment: eight are
`DID NOT WARN` under pytest 9 where napari asks for >= 8.3.5.

## `parallel.py` — worker threads, results handed to the GUI thread

```
### PYTHON_GIL=1                  ### PYTHON_GIL=0
  threads= 1    0.41s   1.00x       0.42s   1.00x
  threads= 2    0.41s   0.99x       0.22s   1.86x
  threads= 4    0.41s   0.99x       0.13s   3.15x
  threads= 8    0.41s   1.00x       0.08s   5.26x
```

Pure Python work on purpose - numpy would release the GIL by itself and
the comparison would measure nothing.

## `toolkits.py` — what the handover costs (`PYTHON_GIL=0`)

```
                  no GUI        tkinter       PySide6
  threads= 1    0.41s 1.00x   0.41s 1.00x   0.41s 1.00x
  threads= 2    0.22s 1.88x   0.22s 1.90x   0.24s 1.74x
  threads= 4    0.13s 3.12x   0.14s 2.92x   0.13s 3.11x
  threads= 8    0.08s 5.20x   0.06s 7.22x   0.07s 5.57x
```

One band. The handover is not the limit.

## `scaling.py` — QObjects do not scale, by design

```
### PYTHON_GIL=1                  ### PYTHON_GIL=0
  threads=  1    1.76s   1.00x      1.70s   1.00x
  threads=  2    2.21s   0.80x      1.56s   1.09x
  threads=  4    3.07s   0.57x      1.89s   0.90x
  threads=  8    5.51s   0.32x      2.93s   0.58x
  threads= 16    5.94s   0.30x      3.19s   0.53x
```

Neither column scales, and that is the intended outcome: Qt is not
thread-safe per object, so the binding serializes what reaches one object.
What free threading buys an application is the *other* work running beside
the GUI, which is what `parallel.py` measures. In absolute terms it still
wins here, about 2x at eight threads, because the GIL column pays for
contention on top.

## `callcost.py`, `lockcost.py` — what the guard costs

```
guard on  : 300000 calls in 0.093s = 311 ns/call
guard off : 300000 calls in 0.091s = 304 ns/call

obj.objectName()                 232.0 ns/call
with lock: obj.objectName()      332.8 ns/call
with lock: pass                  100.2 ns/call
```

7 ns, about 2%. The same lock taken from Python costs 100 ns; that gap is
why the guard sits in C++.

## `falsesharing.py` — the stripe table stays unpadded

```
threads=8 iters=200000 stripes=1024
  same cache line  median  1.880s   range 1.843-1.892
  different lines  median  1.861s   range 1.845-1.884
  natural          median  1.903s   range 1.878-1.922
```

Within 2%, ranges overlap. Padding would cost 64 KB and buy nothing.

## `qt_race.py` — the locks earn their place

Eight threads, 2000 iterations. With every lock in place, all four
scenarios survive: `slot_registration`, `connect_disconnect`,
`shared_reader`, `shared_setter`.

`shared_setter` calls a Qt setter on one object from eight threads, the
case Qt does not allow. Same binary, guard switched off:

```
guard on  (PYSIDE6_OPTION_FT unset)   : 5 runs, 5 clean
guard off (PYSIDE6_OPTION_FT=0b011)   : 5 runs, 5 SIGABRT
```

A lock that can never be removed proves nothing. This one can be, and the
scenario then dies every time.

## `gilscan.py` — packages that re-enable the GIL

Every top-level package imported in its own process, because the flag is
process-wide and never goes back.

```
probed 73 top-level packages

bermuda:
    The global interpreter lock (GIL) has been enabled to load module
    'bermuda._bermuda', which has not declared that it can run safely
    without the GIL.
```

Two more that a top-level scan cannot see:

- `vispy.visuals.text._sdf_cpu` — napari reaches it as soon as it draws
  text. A pure numerical routine (8SSEDT distance transform).
- `numcodecs` — no free-threaded wheel at all, which takes `zarr` with it.

What decides is the `Py_mod_gil` slot in the module definition; without it
the interpreter re-enables the GIL for the whole process on import. The
language does not matter - bermuda is Rust (207 PyO3 symbols), and CPython
sees an ordinary extension. Each generator spells the declaration its own
way:

| built with | declaration |
|---|---|
| plain C | `{Py_mod_gil, Py_MOD_GIL_NOT_USED}` in the slot array |
| Cython 3.1 | `# cython: freethreading_compatible=True` |
| PyO3 >= 0.23 | `#[pymodule(gil_used = false)]` |

It is a promise, not a check: the interpreter takes it at its word. These
look like packages nobody has got around to declaring rather than packages
that would be unsafe to declare. `PYTHON_GIL=0` overrides all three
meanwhile.

Everything else in the napari stack was fine: numpy, scipy, pandas,
scikit-image, aiohttp, rapidfuzz, napari-metadata.
