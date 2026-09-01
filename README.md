# Free-threading measurements for PySide6

The scripts behind the numbers in the
[preview release](https://github.com/ctismer/pyside6-freethreading/releases/tag/v6.12.0a1-ft-preview1),
so that anyone can repeat them instead of taking them on trust.

Nothing here is part of PySide6. It is a working set, published because
repeating a measurement is worth more than reading its result.

## Setting up

A free-threaded CPython 3.14, the wheels from the release, and napari from
git:

```
python -m venv ftvenv
ftvenv/bin/pip install shiboken6-*.whl pyside6_essentials-*.whl
git clone https://github.com/napari/napari
ftvenv/bin/pip install -e napari          # no Qt extra: pip would fetch PyQt
ftvenv/bin/pip install pytest pytest-qt pytest-timeout pytest-pretty \
    pytest-rerunfailures hypothesis pretend napari-plugin-manager \
    napari-metadata bermuda rapidfuzz aiohttp
export QT_API=pyside6
```

`zarr` is missing on purpose: `numcodecs` has no free-threaded wheel yet,
so one test file has to be excluded below.

## The napari run

```
cd napari
PYTHONPATH=/path/to/this/repo QT_API=pyside6 PYTHON_GIL=0 \
  ftvenv/bin/python -m pytest src/napari/_qt -q -s \
    --timeout=120 --maxfail=0 -p gilcheck_plugin \
    --ignore=src/napari/_qt/dialogs/_tests/test_reader_dialog.py
```

Run it once like that and once with `PYTHON_GIL=1`. The point is not that
it passes, it is that both runs agree: 906 passed, 12 failed, and the same
12. Those twelve are the environment - eight are `DID NOT WARN` under
pytest 9 where napari asks for >=8.3.5 - and they fail with the GIL on as
well.

`-s` matters. pytest swallows stderr for passing tests, and without it the
plugin's verdict never reaches you.

## The scripts

`RESULTS.md`
: The output of all of these, produced in one sitting, so the numbers can
  be read without building anything.

`gilcheck_plugin.py`
: A pytest plugin that reports whether the GIL was disabled for the whole
  session. Useful far beyond PySide: a run is only free-threaded if
  nothing switched the GIL back on, and that is worth checking rather than
  assuming.

`gilscan.py`
: Imports every top-level package in the environment in its own process
  and reports which ones re-enable the GIL. This is how the list below was
  made.

`parallel.py`
: Python work in worker threads, each result handed to the GUI thread by
  queued signal - the shape `napari`'s thread_worker uses. The work is
  deliberately pure Python; numpy would release the GIL by itself and the
  comparison would measure nothing. With the GIL: 1.0 / 1.0 / 1.0 / 1.0 on
  1, 2, 4, 8 threads. Without: 1.0 / 2.0 / 3.1 / 5.4.

`toolkits.py`
: The same load handed over three ways - no GUI, tkinter, PySide6 - to see
  what the handover costs. All three land in one band, so it costs little.
  Keep each measurement in the seconds: a first version ran 0.06s per
  point and produced pure noise.

`qt_race.py`
: Four concurrency scenarios. Three are clean. `shared_setter` calls a Qt
  setter on one object from eight threads, which Qt does not allow, and it
  is there to mark where the binding's protection ends.

`scaling.py`, `falsesharing.py`, `callcost.py`, `lockcost.py`
: How far various shapes scale, and what the per-object lock costs. The
  false-sharing one reads object addresses to sort them into groups that
  share a cache line and groups that do not.

`napari_stress.py`, `napari_ab.py`
: A stress driver built on napari's own worker machinery, and an A/B
  runner for it. Incomplete: the driver keeps its objects thread-local, so
  they are never shared and the unguarded column does not crash. Left in
  because the shape is right and the gap is worth knowing.

## Packages without free-threading support

Found while getting napari to run:

- `numcodecs` — no free-threaded wheel, which takes `zarr` with it.
- `vispy.visuals.text._sdf_cpu` — no free-threading declaration, so
  importing napari switches the GIL back on for the whole process. The
  module is a pure numerical routine (an 8SSEDT distance transform); it
  looks safe, it just does not say so. Cython 3.1 needs one line,
  `freethreading_compatible=True`. `PYTHON_GIL=0` overrides it meanwhile.

- `bermuda._bermuda` — no free-threading declaration either. It came into
  the environment later than the first scan, which is why an earlier
  version of this file claimed there were none; see `RESULTS.md` for the
  scan as it stands.

Everything else in the napari stack was fine: numpy, scipy, pandas,
scikit-image, aiohttp, rapidfuzz, napari-metadata. All 73 top-level
packages are checked individually by `gilscan.py`.
