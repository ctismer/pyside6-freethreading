# Free-threaded builds

CPython can be built without the global interpreter lock (GIL). Such a
free-threaded interpreter is installed under its own name, for example
`python3.14t`, and PySide can be built with it. The support is experimental and
opt-in: only a build made with a free-threaded interpreter has it. A build made
with a regular interpreter (a GIL build) compiles exactly the same code as
PySide without free-threading support, and everything below applies to
free-threaded builds only.

Some terms used below: a wrapper is the Python object that stands for a C++
object. A QObject is owned by Python when PySide deletes it together with its
wrapper. A thread is attached while it may run Python code (in CPython's terms,
it holds a thread state). A measure is one change that makes PySide safe
without a GIL; each measure can be switched off for testing (see "Building and
testing").

## What changes

- Importing PySide does not switch the GIL on and prints no warning. In a
  free-threaded interpreter, each extension module states in its `Py_mod_gil`
  slot whether it needs the GIL; importing a module that does not declare
  `Py_MOD_GIL_NOT_USED` switches the GIL on for the whole process and prints a
  `RuntimeWarning`. The code generator shiboken writes that declaration into
  the PySide6 and shiboken6 modules when they are compiled for a free-threaded
  interpreter; the handwritten module QtQmlFeatures declares it in its own
  source. If the interpreter is started with `PYTHON_GIL=1` or `-X gil=1`,
  the GIL is on anyway; all measures stay in effect, and lazy loading and
  `__feature__` stay unavailable, since a free-threaded build is compiled
  without them.
- The shared data named in this section is protected against concurrent access.
  Other shared state of the bindings is not covered yet; see the limits below.
  The parent/child relations between objects and the ownership of their C++ objects
  are protected by one lock, the state lock. Under the state lock only short
  bookkeeping in C++ runs: no Python code, no change of a reference count that
  could free an object, and no other lock. Other shared data has its own lock:
  the map from C++ objects to their wrappers, the registries of types and
  converters, the bookkeeping of signals and slots, the construction of QML
  types, and the dynamic types of Qt Remote Objects. Under most of these locks
  no Python runs, so their holder never needs the GIL, and a thread that has to
  wait for one stays attached. Where Python can run under a lock, as under
  those of one-time initializations and of the dynamic types of Qt Remote
  Objects, a waiting thread detaches, as CPython's own locks do, because the
  holder may need the GIL. Type creation changes no type object others share.
- A QObject owned by Python is deleted in the thread it belongs to. The last
  reference to its wrapper can be dropped in any thread, for example by the
  garbage collector, which runs in whichever thread triggers it, and Qt
  considers deleting a QObject outside its own thread unsafe while that thread
  may process events. When the QObject belongs to another thread that is still
  running, PySide therefore hands the deletion to that thread with
  `deleteLater()` (see the limits below). A QObject of the current thread, or
  of a thread that has already finished, is deleted immediately, as in a GIL
  build.
- Lazy loading is switched off. With lazy loading, a type is only created when
  it is first used; in free-threaded builds an import creates all types of its
  module at once, and the environment variable `PYSIDE6_OPTION_LAZY` has no
  effect. Lazy loading patches Python's module type, the type of all modules,
  and redirects imports for the whole process, which is not safe while several
  threads import at the same time.
- `__feature__` is not available: `from __feature__ import ...` raises
  `ImportError`, so `snake_case` and `true_property` cannot be used. Each
  module selects its features, but the PySide classes have one set of attribute
  dictionaries per process, which PySide exchanges for the selection of the
  module that is calling. Another thread would see the dictionaries change in
  the middle of its work.
- `Shiboken.dumpTree()` raises `NotImplementedError`. It walks the tree of
  parent and child objects below an object and lists the C++ base classes of
  each one. The tree is protected by the state lock, but listing the base
  classes reads the Python type objects of the class hierarchy, which
  libshiboken never does while it holds the state lock. Without the lock, the
  garbage collector, running in another thread, could change the tree during
  the walk.
- `Shiboken.replaceModuleDict()` leaves the module unchanged and returns
  `False`. In a GIL build, PySide6's `__init__.py` calls it to give the
  `PySide6` package a new module class and a dictionary that computes `__all__`
  on first access. It replaces the dictionary first and the class second, so
  another thread could see the module with the new dictionary but the old
  class. A free-threaded build computes `__all__` during the import instead.
  The function returns `False` rather than raising, so that `__init__.py` stays
  the same for both builds.
- A method connected twice to the same signal gives two connections, and PySide
  keeps track of both: disconnecting the method once removes one of them,
  disconnecting it again removes the other, and deleting the receiver removes
  both. In a GIL build, the second disconnect fails with a `RuntimeWarning`,
  and after the receiver is deleted one of the two connections stays and is
  still called.
- A slot that is a method of an object without support for weak references (for
  example an instance of a class with `__slots__` but no `__weakref__`) keeps
  that object alive until it is disconnected: the connection holds the bound
  method, and the bound method holds the object. For other receivers, the
  connection has only a weak reference and holds the receiver while a signal is
  delivered to it. Without a weak reference, PySide could not tell whether the
  object has been freed in the meantime. In a GIL build, such an object is
  freed while it is still connected, and emitting the signal afterwards
  crashes.
- A `list`, `dict` or `set` itself, not a subclass of one, passed to a
  generated wrapper for a parameter whose C++ type is a container is copied
  before it is converted. A GIL build converts the argument directly. A
  free-threaded build first makes a shallow copy (a new list, dict or set with
  the same items), converts the copy and keeps it until the call returns; if the
  copy cannot be made, it converts the original, as a GIL build does. The items
  themselves are not copied. Changes that another thread makes to the original
  during the call do not reach the call, and an item that the other thread
  removes from the original is not freed while the call still uses it.

## Limits

- Qt's thread rules apply as in C++. A QObject lives in its thread, and PySide
  adds no checks for using it from another one.
- Changing a PySide class, or a Python subclass of one, at runtime while other
  threads use it, for example assigning its attributes or its `__bases__`, is
  not supported.
- Not all shared state of the bindings is protected yet. Much of it is older
  than the free-threading support, for example the Python message handler of
  `qInstallMessageHandler()` and some caches that are filled on first use.
- A Qt message handler written in Python must not wait for a thread that reads
  a `RepFile` of QtRemoteObjects: Qt may call the handler while that type
  registry is locked.
- A QWidget, QWindow or QQuickItem whose wrapper goes in another thread is
  deleted later in the main thread, as in a GIL build. From then on, a stored
  signal of it raises the same `RuntimeError` as a signal of a deleted object;
  in a GIL build it still works until the main thread has deleted the object.
- When the last reference to the wrapper of a QObject goes in another thread
  than the QObject's own, and that thread is still running, the deletion runs
  only when the owner thread processes deferred deletions: in its event loop
  (`exec()`) or through `QCoreApplication.sendPostedEvents(None,
  QEvent.DeferredDelete)`. Calling `processEvents()` without a running event
  loop does not process them (see the Qt documentation of
  `QCoreApplication.processEvents()`). If the owner thread never processes
  them, for example the main thread of a script that never calls `exec()`, such
  an object stays alive, and it is not deleted at exit either. A signal of that
  object that is still referenced, for example a bound signal stored earlier,
  raises the same `RuntimeError` as a signal of a deleted object, as it would
  in a GIL build, where the object would already be gone. An emit, connect or
  disconnect that runs while another thread drops the last reference keeps the
  object until it is done.
- `fork()` after the bindings were used is not supported: their locks are
  process-wide and have no fork handler, so a lock another thread held stays
  locked in the child. Use the `spawn` start method of `multiprocessing`, or
  `fork` followed by `exec`.
- Free-threaded builds need CPython 3.14.7t or a later 3.14t and were tested
  with 3.14.10t; other free-threaded versions are not supported. Before 3.14.7,
  interning a string can detach the thread, and some one-time initializations of
  the bindings intern strings. For GIL builds, the code shiboken writes was
  compared with Python 3.12 and 3.15, which use different forms of the module
  definition, against the code without free-threading support, with
  `tools/gil_view.py`: it resolves only `Py_GIL_DISABLED` and ignores comments,
  whitespace and the order of generated definitions. The code differs where a
  wrapper lookup returns a `Shiboken::WrapperRef`, which borrows in a GIL build,
  as before.

## Building and testing

Build with a free-threaded interpreter and without the limited API. The header
`Python.h` of 3.14t rejects the limited API in a free-threaded build, and the
build uses the limited API unless told otherwise:

```bash
python3.14t setup.py build --limited-api=no
```

CMake recognizes a free-threaded interpreter by the `t` in its ABI tag. It then
adds the free-threading sources to libshiboken and passes shiboken the keyword
`py_gil_disabled`, which PySide's typesystem files test as a condition for
free-threaded code. Every build passes `--module-uses-gil=auto`: the module
declares that it does not use the GIL when it is compiled for a free-threaded
interpreter. Otherwise it declares that it uses the GIL with Python 3.15 and
later, and declares nothing before 3.15, which means the same.

Other bindings made with shiboken need `--module-uses-gil=auto` as well, or the
attribute `module-uses-gil="auto"` on their `typesystem` element; the attribute
takes precedence over the command line option. The default is `yes`, and
importing a module that uses the GIL switches the GIL back on for the whole
process, unless the GIL is forced off with `PYTHON_GIL=0` or `-X gil=0`.
`auto` only declares the module free of the GIL: the wrapped C++ code, the
injected code and the callbacks into Python have to be thread-safe on their
own, so review a binding before declaring it.

The tests run with `testrunner.py` as usual. Tests that make sense only in a
free-threaded build either skip themselves in a GIL build, or are added in
CMake only for free-threaded builds. Most of them are in
`sources/pyside6/tests/pysidetest/` (`*_freethreading_test.py`,
`state_lock_test.py` and others) and in
`sources/shiboken6/tests/samplebinding/*_freethreading.py`.

Each measure has an option bit in `Shiboken::FreeThreading::Option`. The
environment variable `PYSIDE6_OPTION_FT` selects the bits: unset or `on` means
all of them, `off` none, a number (decimal, or with `0x` hexadecimal, with `0b`
binary) exactly the bits set in it, and `~` followed by a number all bits
except those. Clearing a bit is a testing device; only all bits set is
supported. A counter-proof is a test that shows that a measure is needed: it
passes with all bits set and, when the bit of the measure is cleared, fails on
the defect the measure prevents. A debug build also has failpoints, which stop
a thread at a known place so that a second thread reaches the same object in a
known order. The tests that use failpoints and the counter-proofs of the bits
(all but ModuleRegistryLock, which has none) are in
`sources/pyside6/tests/manually/freethreading/`; its `README.md`
explains how to run them.

## Changing the code

Free-threaded code sits behind `#ifdef Py_GIL_DISABLED`, and the code of a GIL
build stays as it was. `tools/gil_view.py --check` resolves those conditionals
for a GIL build and compares the result with the commit the change is based on:
it fails when a change alters code that a GIL build compiles, and ignores
changes in comments. A new measure gets an option bit and a counter-proof, or a
stated reason why no counter-proof can exist. Code that only switches a feature
off in free-threaded builds, such as lazy loading or `__feature__`, needs no
bit: there is nothing to protect, the feature is simply not available.

## Reference

- [Free-threaded builds](../shiboken6/libshiboken/freethreading.html): the
  measures of libshiboken and their option bits
- [The state lock](../shiboken6/libshiboken/freethreading-statelock.html)
- [libpyside](../pyside6/libpyside/libpyside-module.html) and
  [libpysideremoteobjects](../pyside6/libpysideremoteobjects/libpysideremoteobjects-module.html)
- [PEP 703](https://peps.python.org/pep-0703/), which describes the
  free-threaded interpreter
