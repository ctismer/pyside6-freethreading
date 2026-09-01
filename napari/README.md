# napari on free-threaded PySide6

napari from git, CPython 3.14.3t, our PySide6 6.12.0a1 cp314t wheels.

## The suite says the same in both columns

| | tests | passed | failed | errors | skipped |
|---|---|---|---|---|---|
| `PYTHON_GIL=1` | 984 | 906 | 12 | 2 | 64 |
| `PYTHON_GIL=0` | 984 | 906 | 12 | 2 | 64 |

[gil1](../data/napari/suite-gil1.xml) ·
[gil0](../data/napari/suite-gil0.xml)

The point is not that it passes. It is that both columns agree: the same
twelve fail either way, so they belong to the environment. Eight are
`DID NOT WARN` under pytest 9 where napari asks for >= 8.3.5; the rest are
a screenshot test on a zero-size window and its neighbours.

```
cd napari
PYTHONPATH=/path/to/this/repo QT_API=pyside6 PYTHON_GIL=0 \
  venv/bin/python -m pytest src/napari/_qt -q -s \
    --timeout=120 --maxfail=0 -p gilcheck_plugin \
    --ignore=src/napari/_qt/dialogs/_tests/test_reader_dialog.py
```

Once like that, once with `PYTHON_GIL=1`. `-s` matters: pytest swallows
stderr for passing tests, and without it the plugin's verdict never
reaches you. `zarr` is missing on purpose - `numcodecs` has no
free-threaded wheel, which is why one test file is excluded.

## What re-enables the GIL here

`vispy.visuals.text._sdf_cpu` has no free-threading declaration, and napari
reaches it as soon as it draws text - so a napari run is only free-threaded
with `PYTHON_GIL=0`. It is a pure numerical routine, an 8SSEDT distance
transform: it looks safe, it just does not say so. `bermuda._bermuda`
(Rust/PyO3) is the second, and it shows up on import.

## Scripts

`nap_demo.py`
: Opens a viewer and reports the GIL state before and after.

`napari_stress.py`, `napari_ab.py`
: A stress driver built on napari's own worker machinery, and an A/B
  runner for it. Incomplete, and left in on purpose: the driver keeps its
  objects thread-local, so nothing is shared and the unguarded column does
  not crash. The shape is right, the gap is worth knowing.

## What this run does not say

napari does most of its Qt work in one thread. It shows that free
threading costs nothing here, not that it gains anything - for that see
`parallel.py` in [RESULTS.md](../RESULTS.md), and Spyder, which really
does run worker threads.
