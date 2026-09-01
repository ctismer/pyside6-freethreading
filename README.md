# Free-threading measurements for PySide6

The scripts behind the numbers in the
[preview release](https://github.com/ctismer/pyside6-freethreading/releases/tag/v6.12.0a1-ft-preview1),
so that anyone can repeat them instead of taking them on trust.

Nothing here is part of PySide6. It is a working set, published because
repeating a measurement is worth more than reading its result.

## Setting up

A free-threaded CPython 3.14 and the wheels from the release:

```
python -m venv ftvenv
ftvenv/bin/pip install shiboken6-*.whl pyside6_essentials-*.whl
export QT_API=pyside6
```

That is enough for every script at the top level. The two applications
need more, and each says so on its own page: [napari](napari/README.md),
[Spyder](spyder/README.md).

## The scripts

`RESULTS.md`
: Every result on one page, each number linking to the run it came from.
  Start there.

`napari/`, `spyder/`
: One page per application - what was run, what it says, and what it does
  not say - next to the scripts that produced it.

`data/`
: The output verbatim: the measurement scripts, napari's junit files, and
  Spyder's suite per test file for all three columns.

`gilcheck_plugin.py`
: A pytest plugin that reports whether the GIL was disabled for the whole
  session. Useful far beyond PySide: a run is only free-threaded if
  nothing switched the GIL back on, and that is worth checking rather than
  assuming.

`gilscan.py`
: Imports every top-level package in the environment in its own process
  and reports which ones re-enable the GIL. The offenders it found are
  listed in `RESULTS.md`.

`parallel.py`
: Python work in worker threads, each result handed to the GUI thread by
  queued signal - the shape `napari`'s thread_worker uses. The work is
  deliberately pure Python; numpy would release the GIL by itself and the
  comparison would measure nothing.

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

The per-application scripts live next to their page, in `napari/` and
`spyder/`.
