# Results

Measured 2026-09-01. Every number links to the run it came from; `data/`
holds the output verbatim.

```
python 3.14.3 free-threading, and 3.14.3 with the GIL from the same recipe
PySide6 6.12.0a1 preview wheels, Qt 6.12.0
arm64, macOS 14.7, 10 cores (8 performance + 2 efficiency)
```

Every comparison runs the same wheels twice, switched by `PYTHON_GIL`. The
lock experiments switch our own locks off with `PYSIDE6_OPTION_FT` in the
same binary. No rebuild sits between any two columns.

## Applications

Re-measured 2026-09-03 against the final series, with wheels built from it
for both interpreters. Machine: M3, macOS 14.8, 12 cores.

| | with the GIL | without | |
|---|---|---|---|
| [napari](napari/), 1381 tests | 12 failed, 1 error | identical set, test for test | [details](napari/README.md) |
| [Spyder](spyder/), 2374 tests | 52 failed, 8 errors | 52 failed, 7 errors | [details](spyder/README.md) |

**No test fails free-threaded that passes with the GIL** - in either
application. napari's twelve are the same twelve either way. Spyder differs
in one test, and it fails on the *GIL* side: a remote-explorer test that
needs an ssh client.

Spyder runs against a **GIL twin**: the same PySide6 source built for a GIL
interpreter of the same version, against the same Qt, so a difference cannot
be blamed on a Qt, PySide6 or Python version. Both wheel sets were rebuilt
for this run rather than compared across dates.

The napari count grew from the 984 of the 2026-09-01 run because the runner
now takes `src/napari/_tests` as well as `src/napari/_qt`, and no longer
ignores `test_reader_dialog.py`. Same code, wider selection; the twelve
failures are the same ones.

## Threads

| | with the GIL | without | data |
|---|---|---|---|
| `parallel.py`, 1/2/4/8 threads | 1.00 1.00 1.00 1.00 | 1.00 1.86 3.15 5.26 | [txt](data/measurements/parallel.txt) |
| `toolkits.py` at 8 threads, no GUI / tkinter / PySide6 | - | 5.20 / 7.22 / 5.57 | [txt](data/measurements/toolkits.txt) |
| `scaling.py`, QObjects, 8 threads | 0.32 | 0.58 | [txt](data/measurements/scaling.txt) |

## The locks

| | | data |
|---|---|---|
| `callcost.py`, guard on / off | 311 / 304 ns per call | [txt](data/measurements/callcost.txt) |
| `lockcost.py`, the same lock from Python | 100 ns | [txt](data/measurements/lockcost.txt) |
| `falsesharing.py`, same cache line / apart | 1.880 / 1.861 s, ranges overlap | [txt](data/measurements/falsesharing.txt) |
| `qt_race.py`, `shared_setter`, guard on / off | 5 of 5 clean / 5 of 5 SIGABRT | [txt](data/measurements/qt_race.txt) |

## Sanitizers

Full detail in [sanitizers/](sanitizers/); the logs of every run are under
`ft-apps/sanitizer-runs/`.

| | reports | |
|---|---|---|
| ThreadSanitizer, 13 scenarios, both machines | findings 1-3 only | [details](sanitizers/tsan.md) |
| ThreadSanitizer, the whole pyside6 suite, 543 tests | **0** | [details](sanitizers/tsan.md) |
| AddressSanitizer, 13 scenarios, both machines | finding 5 only | [details](sanitizers/asan.md) |
| AddressSanitizer, the whole suite, both machines | 5 = one finding, twice | [details](sanitizers/asan.md) |

What is left after both tools is `feature_select.cpp` /
`sbkfeature_base.cpp` and two static caches in the generated wrappers.
The state lock, the call leases, the binding manager and destruction are
blank under both. Findings 5 and 6 fail with the GIL as well and on a
released wheel, so they are release bugs rather than free-threading ones.

Taking a lock away is what shows it is needed: `move_to_thread` crashes
5 of 5 without the state lock and 0 of 5 with it, `container_convert` the
same against the lazy type lock - the
[kill-switch matrix](sanitizers/stress.md#what-the-kill-switch-measured).

## Packages that re-enable the GIL

One import without a free-threading declaration turns the GIL back on for
the whole process, and it never goes off again. Found so far:

| | reached by | |
|---|---|---|
| `lxml.etree` | Spyder, during startup | [how](spyder/README.md) |
| `vispy.visuals.text._sdf_cpu` | napari, as soon as it draws text | [how](napari/README.md) |
| `bermuda._bermuda` (Rust/PyO3) | napari, on import | [txt](data/measurements/gilscan.txt) |
| `numcodecs` | no free-threaded wheel at all, takes `zarr` with it | |

`gilscan.py` imports every top-level package in its own process and names
the offenders. What decides is the `Py_mod_gil` slot; the language does
not matter.

| built with | declaration |
|---|---|
| plain C | `{Py_mod_gil, Py_MOD_GIL_NOT_USED}` in the slot array |
| Cython 3.1 | `# cython: freethreading_compatible=True` |
| PyO3 >= 0.23 | `#[pymodule(gil_used = false)]` |

## Two numbers that read wrong on their own

**QObjects do not scale, and that is the intended outcome.** Qt is not
thread-safe per object, so the binding serializes what reaches one object.
What free threading buys an application is the other work running beside
the GUI - `parallel.py`, not `scaling.py`.

**A `Py_mod_gil` declaration is a promise, not a check.** The interpreter
takes it at its word. The packages above look like nobody has got around
to declaring them, not like packages that would be unsafe to declare.
