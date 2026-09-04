# ThreadSanitizer

Two passes, 03.09. and 04.09.2026. The second one ran on both build
machines with identically built trees, and it is the one that counts —
the first had an uninstrumented libpython underneath.

Logs: [`../ft-apps/sanitizer-runs/`](../ft-apps/sanitizer-runs/) —
`0903-tsan-scenarios`, `0904-tsan-Deep-Thought-1`, `0904-tsan-Amrumer-1`,
`0904-suite-tsan-Deep-Thought-1`.

## What came back

| run | scenarios | reports |
|---|---|---|
| 03.09., uninstrumented libpython | 8 | 16, several of them the interpreter |
| 04.09., both machines | 13 | findings 1–3 only |
| 04.09., the whole pyside6 suite (543 tests, 1:18 h) | — | **0** |

Everything ThreadSanitizer still reports lives in two files:
`sbkfeature_base.cpp` and the static caches in the generated wrappers.
The state lock, the call leases, the binding manager and destruction —
what phase 1 built — are blank under it, in the scenarios and across the
suite.

## The failure that would have invalidated the numbers

The first run of the second pass picked `3.15.0b3t` instead of the
instrumented `3.15.0b4t-tsan`. Both carry the same extension suffix
`.cpython-315t-darwin.so`, and the runner only matched on that. The
output looked like findings:

```
shared_delete   2 reports   basewrapper.cpp:2336 2343 2468
signal_race     9 reports
```

Same tree, same minute, with the instrumented interpreter:

```
shared_delete   0 reports
signal_race     7 reports   (findings 2 and 3)
```

Without an instrumented libpython, ThreadSanitizer cannot see the
happens-before edges CPython establishes and reports the interpreter
rather than us. In the log that is indistinguishable from a real finding.
`sanitize.sh` now takes the named interpreter first and refuses one whose
`CONFIG_ARGS` lack `--with-thread-sanitizer`.

## Finding 1 — feature switching saves and restores a global

`sbkfeature_base.cpp:72`, `initSelectableFeature()`, reported in five of
the eight scenarios:

```cpp
static SelectableFeatureHook SelectFeatureSet = nullptr;

SelectableFeatureHook initSelectableFeature(SelectableFeatureHook func)
{
    auto ret = SelectFeatureSet;
    SelectFeatureSet = func;
    ...
}
```

It is used as save-and-restore around type creation, in
`basewrapper.cpp:777/783` and `sbkmodule.cpp:317/327`, with the intent
from PYSIDE-1463: "Prevent feature switching while in the creation
process."

Two nested pairs on two threads lose the value:

```
T1: save = hook;     SelectFeatureSet = nullptr
T2: save = nullptr;  SelectFeatureSet = nullptr    <- remembers the wrong one
T1:                  SelectFeatureSet = hook
T2:                  SelectFeatureSet = nullptr    <- stays off
```

No crash. `__feature__` silently stops switching. The kind of defect no
test suite finds and a user experiences as "snake_case is sometimes
gone".

## Findings 2 and 3 — the static caches in the generated wrappers

`basewrapper.cpp:922/927`, `overrideMethodName()`:

```cpp
PyObject *pyMethodName = nameCache[is_snake];  // borrowed
if (pyMethodName == nullptr) {
    pyMethodName = Shiboken::String::getSnakeCaseName(methodName, is_snake);
    nameCache[is_snake] = pyMethodName;
}
```

`nameCache` is a static field in the generated wrapper, one per virtual
method. Finding 3 is the result cache of the same function,
`basewrapper.cpp:937` read against `:1001` written, `Sbk_GetPyOverride`,
parameter `PyObject *&resultCache`. Both are reached through
`QObjectWrapper::connectNotify()`, i.e. `connect()` from several threads
at once.

**Honest damage assessment.** Both caches hold immutable objects. Two
threads that race compute the same thing and one overwrites the other
with an equivalent value. What remains is a reference leak per lost race
(both increfed, only one will ever be released) and formally undefined
behaviour, because a non-atomic pointer is written and read at the same
time. On arm64 that access is indivisible in practice; it is not
guaranteed. No crash expected — worth reporting, not worth holding a
release.

## Finding 4 — `SbkObject_GetDict_NoRef`, basewrapper.cpp:175

From the suite run, not from the scenarios. Check-then-act on a bare
`PyObject *`:

```cpp
if (!sbkObj->ob_dict) {              // both threads see nullptr
    Shiboken::GilState state;
    sbkObj->ob_dict = PyDict_New();  // both create one, one wins
}
return sbkObj->ob_dict;
```

The counterpart in the report is a read from `PyObject_GenericGetAttr`
through `SbkObject_GenericGetAttr`; the caller is `Sbk_GetPyOverride`
(basewrapper.cpp:989), the lookup of a Python override of a virtual
method.

**No damage demonstrable.** `../ft-apps/dict_race.py` drives exactly this
pattern — a fresh subclass per round, half the threads triggering the
virtual call, the other half setting attributes:

```
GIL on    3x   12000 attributes, 0 lost
GIL off   3x   12000 attributes, 0 lost
```

The race is real, the consequence is not measurable. Worth fixing (a CAS
or the state-lock transaction is enough), but it is not a crash.

## The crash that came out of finding 1

`../ft-apps/feature_race.py`: four threads create QObject subclasses, one
thread has `from __feature__ import snake_case` and creates instances.

```
GIL on     3 of 3 clean      11053 / 24249 / 24912 checks
GIL off    5 of 5 crash      Segmentation fault: 11
```

Without the feature import the same setup survives 3 of 3, so it is the
feature system and not type creation. Time-of-check-to-time-of-use on the
global `featurePointer`, two lines apart in `feature_select.cpp`:

```
373:    if (featurePointer == nullptr)   // checked
374:        return;
375:    auto *type = Py_TYPE(obj);
376:    SelectFeatureSet(type);          // used, nulled meanwhile
```

Nulled by the save-and-restore of finding 1: `_setupNew()` calls
`initSelectableFeature(nullptr)`, which calls `featureEnableCallback(false)`,
which sets `featurePointer = nullptr` — on **every** type creation. The
intent of PYSIDE-1463, keeping feature switching out of the creation
process, is itself the cause under concurrency: one thread switches off
globally while another sits inside `Select()`.

**Not ours.** Independent of every lock phase 1 adds:

```
PYSIDE6_OPTION_FT=0b111 (all locks)      3/3 crashes
PYSIDE6_OPTION_FT=0b011 / 0b101 / 0b110  3/3 each
PYSIDE6_OPTION_FT=off                    3/3
```

In a file the chain never touched. Not a regression — a gap of its own,
and the free-threading design document does not mention `__feature__` at
all, so it neither promises nor excludes it. Two ways out, both to be
weighed: make `featurePointer` and `SelectFeatureSet` thread-local (the
save-and-restore means "while *this* thread creates a type" anyway), or
disable feature switching under free threading and say so.

## The whole suite: nothing

Deep-Thought, with the time limit raised (see [stress.md](stress.md) for
why that mattered):

```
shiboken6    158/158  passed
pysidetest    37/37   passed
pyside6      543/543  ran, 15 failures
ThreadSanitizer reports: 0
```

Not one race report across the entire suite. That is the counter-test to
the scenarios: they hammer eight lines at one spot, the suite does
thousands of ordinary things — and finds nothing.

The 15 failures, each one looked at:

```
9x QtAsyncio_*        sanitizer timing (green without it)
3x ***Timeout 60s     pysidetest_pyenum..., registry_existence_test,
                      QtCore_qprocess_test - ctest's per-test limit,
                      too tight under TSan
cpp_interop           starts a C++ app over TCP and waits for the
                      handshake; too slow under TSan. Without it:
                      Passed 1.08 sec
QtUiTools_loadUiType  red without the sanitizer too
pyside6-deploy        red without the sanitizer too
```

Not one failure is a finding. Whoever reports the 15 unchecked reports
ten timeouts.
