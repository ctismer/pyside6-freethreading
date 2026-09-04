# AddressSanitizer

Same trees, same runner, `-fsanitize=address` instead of thread.
Instrumentation verified by `nm`: libshiboken 72, libpyside 72 ASan
symbols. Run on both machines, 04.09.2026.

Logs: [`../ft-apps/sanitizer-runs/`](../ft-apps/sanitizer-runs/) —
`0904-asan-Deep-Thought-1`, `0904-asan-Amrumer-1`,
`0904-suite-asan-Deep-Thought-1`, `0904-suite-asan-Amrumer-1`.

## What came back

| run | reports |
|---|---|
| 13 scenarios, both machines | nothing but finding 5 |
| the whole pyside6 suite, both machines | 5 reports = one finding, twice |

No use-after-free, no overflow, no double free in the lifecycle paths
phase 1 built — not in the five new scenarios either. The two reports
that exist are ordinary PySide bugs that have nothing to do with free
threading; both fail with the GIL as well.

## Two traps on the way in

**`PYTHONMALLOC=malloc` does not exist on a free-threaded 3.15.** It
knows `default` and `mimalloc_debug` only — pymalloc is replaced by
mimalloc under free threading. The usual ASan advice from the CPython
documentation does not apply here, and mimalloc pools as well: for Python
objects ASan sees pooled memory. The C++ allocations in libshiboken and
libpyside — cptr arrays, SbkObjectPrivate, our ground — it still sees.

**Preloading the runtime does not survive ctest.** A suite run over
`testrunner.py` produced first 675, then 1093 "Interceptors are not
working": ctest starts every test with the interpreter CMake was
configured with, and `DYLD_INSERT_LIBRARIES` does not reach it. A
preloaded runtime therefore only helps when you start python yourself.
Hence `3.15.0b4t-asan` — libpython with `--with-address-sanitizer`, built
`--with-pydebug` so the extension suffix stays
`.cpython-315td-darwin.so` — and `build-asan/` rebuilt against it. After
that: zero interceptor errors. The TSan tree never had the problem
because it was built against its instrumented interpreter from the start.

## Finding 5 — a QObject stored as a dynamic property

`dynamic_property`, rc 1, on **both** machines. Not a race, a jump
through a null vtable slot:

```
SEGV on unknown address 0x000000000000 (pc 0x0)
  #1 PySide::getWrapperForQObject(QObject *, PyTypeObject *)  pyside.cpp:866
  #2 QObject_PTR_CppToPython_QObject
  ...
  #8 Sbk_QObjectFunc_property
```

`pyside.cpp:866` is

```cpp
QVariant existing = cppSelf->property(invalidatePropertyName);
```

a virtual call on a QObject that is gone.

**Nothing to do with free threading.** Three lines, one thread:

```python
holder = QObject()
holder.setProperty("p", QObject())
holder.property("p")                 # SIGSEGV
```

`setProperty` puts the QObject into the QVariant of the dynamic property
table. Nothing holds the Python wrapper past that statement, it is
collected, the C++ object goes with it (Python owns what Python created),
and the QVariant keeps a dangling pointer. `property()` converts it back.

Measured, not assumed:

```
PySide6 6.12.0a1, 3.15t, GIL off        segfault
PySide6 6.12.0a1, 3.15t, PYTHON_GIL=1   segfault
PySide6 6.12.0a1, CPython 3.14          segfault
PySide6 6.11.2,   CPython 3.12          segfault   <- released wheel
```

Reproducer: [`../ft-apps/property_qobject_crash.py`](../ft-apps/property_qobject_crash.py),
runs against any PySide6. A release bug, filed on its own.

## Finding 6 — heap-use-after-free in the documentation generator

`QtXmlToSphinx::Table::normalize()`, deterministic, main thread:

```cpp
QtXmlToSphinx::TableCell &cell = row[col];   // reference into the list
...
if (cell.colSpan > 0) {
    for (int i = 0, max = cell.colSpan - 1; i < max; ++i)
        row.insert(col + 1, newCell);        // may reallocate row
    cell.colSpan = 0;                        // writes into freed memory
}
```

`row.insert` invalidates `cell`. ASan reports "WRITE of size 2" — the
`colSpan` field. Without a sanitizer the test passes (measured: `1/1
Test #37: qtxmltosphinx Passed`), so the error is silent. The obvious fix
is to keep the index instead of the reference, i.e. assign to
`row[col].colSpan` after the loop.

Two machines, two separately built trees, the same spot:

```
                        Deep-Thought   Amrumer
reports                       5            5
qtxmltosphinx.cpp:1436        5            5
qtxmltosphinx.cpp:467         5            5
```

The five are the five repetitions of the same test.

## The other twelve failures: ten of them are the sanitizer

`testrunner` stopped with "12 failures were not blacklisted". The same
tests without a sanitizer, same machine:

```
9x QtAsyncio_*          ASan Failed   without: PASSED
QtQml_registertype      ASan Failed   without: PASSED
qtxmltosphinx           ASan Failed   without: PASSED   <- finding 6
pyside6-deploy_test     ASan Failed   without: Failed
QtUiTools_loadUiType    ASan Failed   without: Failed
```

An ASan debug tree runs about ten times slower and the asyncio tests hang
on time limits. Two tests are red independently of the sanitizer and have
nothing to do with this work.
