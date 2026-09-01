# Spyder on free-threaded PySide6

Spyder 6.2.0a3.dev0 from git, CPython 3.14.3t, our PySide6 6.12.0a1 cp314t
wheels.

Spyder is the more interesting of the two applications, because it is
genuinely multi-threaded. `AsyncDispatcher` runs an asyncio loop per worker
thread and hands results to the GUI thread through
`QCoreApplication.postEvent`; on top of that there are QThreads for the
file search, the dataframe editor, the snippet and fallback completion
actors, and Sphinx rendering. A running Spyder has twelve live threads.
That is the shape a per-object lock exists for.

## It runs

Editor, LSP server, kernel spec, file explorer. With `PYTHON_GIL=0`,
`sys._is_gil_enabled()` is still False after 25 seconds - free-threaded,
not merely started.

## lxml turns the GIL back on during startup

Without `PYTHON_GIL=0`, Spyder re-enables the GIL before its main window
exists:

    spyder/utils/qthelpers.py
      -> spyder/utils/icon_manager.py
        -> spyder/utils/svg_colorizer.py:11   from lxml import etree

lxml 6.1.2 ships a `cp314t` wheel - built against the free-threaded ABI -
but `lxml.etree` does not declare `Py_mod_gil`. Of the 131 top-level
packages in the environment it is the only one that does this; the rest of
the stack (numpy, scipy, pandas, matplotlib, pyzmq, cryptography, pyobjc)
installs as cp314t wheels. Of ~150 packages only three had to be built
from source.

## The suite: three columns

| | tests | failed | errors | skipped |
|---|---|---|---|---|
| 3.14.3t, `PYTHON_GIL=1` | 2374 | 52 | 7 | 126 |
| 3.14.3t, `PYTHON_GIL=0` | 2374 | 52 | 7 | 126 |
| 3.14.3 with the GIL, our own build | 2351 | 52 | 8 | 126 |

[gil1](../data/spyder/failures-ft-gil1.txt) ·
[gil0](../data/spyder/failures-ft-gil0.txt) ·
[twin](../data/spyder/failures-twin.txt) ·
[per file](../data/spyder/summary-ft-gil0.txt)

GIL on against GIL off is not merely the same count: it is the same set,
all 59 entries, test for test.
[diff](../data/spyder/compare-gil-on-off.txt)

### Why the twin ran fewer tests, and why three counts exist

The twin's 2351 against 2374 is one crashed file: the process dies in
`spyder.plugins.projects.tests.test_plugin` before pytest writes its junit
file, so those 24 tests appear nowhere in its own tally. The
remaining one is a test that `flaky` retried once more on the twin.

That is also why the numbers here and in `compare.py` differ slightly:

```
junit "tests" attribute   2374 / 2351     the table above
<testcase> elements       2414 / 2388
distinct test names       2371 / 2347     compare.py
```

`flaky` reruns a failing test and writes every attempt as its own
`<testcase>` - twelve names appear more than once,
`test_save_when_completions_are_visible` five times. The comparison
therefore counts distinct names; counting elements would let one retried
test weigh three times.

The third column is the one that carries the argument. Comparing against
PySide6 from PyPI would mix three differences at once - a Qt version, a
PySide6 version and a Python version. So PySide6 was built twice from one
source, against the same Qt 6.12, for CPython 3.14.3 free-threaded and for
CPython 3.14.3 with the GIL. The only difference left is the GIL.

```
free-threaded   2371 ran, 59 bad
GIL twin        2347 ran, 60 bad

bad free-threaded and green on the twin : 0
bad on the twin and green free-threaded : 1
ran in one column only                  : 24
```

[compare](../data/spyder/compare-ft-vs-twin.txt)

Nothing fails free-threaded that passes with the GIL. The one that goes
the other way is `test_automatic_completions_widget_visible`, a completion
popup that has been flaky throughout. The 24 are all
`spyder.plugins.projects.tests.test_plugin`, which the twin crashed on in
that run - see below, because that turned out to be worth chasing.

## One crash class only the GIL builds show

`spyder.plugins.projects.tests.test_plugin` crashed on the twin during the
suite run and not free-threaded. One occurrence is not a finding, so the
file was run 20 times in each configuration:

| | crashes | class |
|---|---|---|
| 3.14.3t, `PYTHON_GIL=0`, our PySide6 | **0** of 20 | - |
| 3.14.3t, `PYTHON_GIL=1`, our PySide6 | 1 of 20 | `PyObject_ClearWeakRefs`, a different one |
| 3.14.3 with the GIL, our PySide6 | 2 of 20 | both the class below |
| 3.14.3 with the GIL, PySide6 6.11.2 from PyPI | 5 of 20 | all five |

Every one of those seven has the same C stack, from the operating system's
crash reports ([matrix](../data/spyder/crash-matrix.txt),
[all classes](../data/spyder/crash-classes.txt)):

```
EXC_BAD_ACCESS  KERN_INVALID_ADDRESS at 0x1

  _PyType_LookupStackRefAndVersion      <- dereferences 0x1
  _PyType_LookupStackRefAndVersion
  _PyObject_LookupSpecial
  PyObject_Dir                          <- dir(obj)
  builtin_dir
  ...
  slot_tp_init                          <- TracebackException.__init__
```

The Python side reaches it through pytest-qt: an exception escapes inside
the Qt event loop, pytest-qt's hook formats it, and CPython's "did you mean
...?" machinery calls `dir()` on the object the AttributeError came from.
The type lookup then walks a type pointer of `0x1`.

Two things follow. It is **not ours**: PySide6 6.11.2 from PyPI carries
none of this work and crashes the same way, more often. And it does **not
happen free-threaded** - 20 clean runs there against 7 crashes across the
two GIL columns.

What we do not know is why. A type pointer of `0x1` is a type that is
half-built or half-gone, and this branch carries a fix for exactly that
shape - "Hand out a lazily created type only when it is finished" - which
is `#ifdef Py_GIL_DISABLED` and therefore compiled out of every GIL build.
That is a plausible connection and nothing more; proving it means building
the twin with that path enabled and running the twenty again.

Two other classes turned up in the same crash reports: three in
`Sbk_QPlainTextEditFunc_firstVisibleBlock` with addresses like `0x401` and
`0x46b` - a dead C++ pointer, the `editor.tests` segfault below - and six
Qt `qFatal` aborts from `ASSERT: "window"` in `qtestkeyboard.h`, which is
pytest-qt typing into an unfocused window.

## Three files take the interpreter down, in every column

| file | free-threaded | GIL twin |
|---|---|---|
| `editor.tests.test_plugin` | SIGSEGV | SIGSEGV |
| `completion.tests.test_configdialog` | SIGABRT | SIGABRT |
| `variableexplorer.widgets.tests.test_arrayeditor` | SIGABRT | SIGABRT |
| `projects.tests.test_plugin` | passes | SIGSEGV |

The first is the sharp one: `test_editorstacks_and_windows` dies in
`codeeditor.py:4615`, `self.firstVisibleBlock()` inside `paintEvent`,
after exactly the same 26 passing tests in every configuration - including
PySide6 6.11.2 from PyPI on CPython 3.12 with a real GIL, and including
our own wheels with all locks removed by `PYSIDE6_OPTION_FT=off`. It is a
pre-existing Spyder/PySide6 problem, worth reporting upstream; Spyder's CI
does not see it, because their default binding is PyQt5 and the macOS jobs
stop at the first failure.

The second passes all its tests and then aborts during interpreter
shutdown with `QThread: Destroyed while thread '' is still running`. The
third hits `ASSERT: "window"` in `qtestkeyboard.h:58` - pytest-qt typing
into a window without focus, an artefact of running on a desktop rather
than headless.

## What did not run

Our Qt 6.12 is built without QtWebEngine, so `PySide6.QtWebEngineCore` does
not exist. That costs `spyder/app/tests` - the main-window integration
tests, the most valuable part of the suite, whose conftest imports
`QtWebEngineWidgets` unconditionally - and three further test modules,
which appear as the 7 errors above. The numbers are for the rest.

## Repeating it

```
./setup-venvs.sh ft            # 3.14.3t + our free-threaded wheels
./setup-venvs.sh twin          # 3.14.3  + our wheels built for the GIL
./run-suite.sh ft-gil1 venv-ft/bin/python   1
./run-suite.sh ft-gil0 venv-ft/bin/python   0
./run-suite.sh twin    venv-twin/bin/python 1
python aggregate.py logs/ft-gil0
python compare.py logs/ft-gil0 logs/twin
```

One pytest process per test **file**, not per directory. A crash then
costs one file instead of every test behind it, so the columns stay
aligned and can be compared test by test. It also keeps windows left
standing by an earlier file from stealing focus from the next one: run as
a directory, sixteen keyboard-shortcut tests fail that pass when the file
runs alone.
