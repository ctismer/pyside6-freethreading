# Sanitizers and stress runs

Where the free-threaded build is put under a sanitizer, and what came
back. One page per tool, updated as runs happen — including the runs that
find nothing, because "we looked and it was clean" is a result too.

| | |
|---|---|
| [tsan.md](tsan.md) | ThreadSanitizer — data races |
| [asan.md](asan.md) | AddressSanitizer — use-after-free, overflows |
| [stress.md](stress.md) | The A/B harness and the kill-switch matrix |

## What is being tested

PySide6 on the `free-threading` branch, against a free-threaded CPython,
with `PYTHON_GIL=0`. Where a lock can be switched off, the run says which
setting it used: `PYSIDE6_OPTION_FT` is a flags word over the locks the
free-threaded build adds, and clearing a bit takes one away.

    LazyTypeLock = 0x1    serializes lazy type creation
    StateLock    = 0x2    the short-lived lock on the binding state
    CallGuard    = 0x4    serializes calls reaching one C++ object

A lock that cannot be taken away proves nothing, which is why it exists.

## How to repeat a sanitizer run

The build takes its flags from the environment at the first CMake
configure, so it needs a **fresh** build directory:

```
export CXXFLAGS="-fsanitize=thread -g -fno-omit-frame-pointer"
export CFLAGS="$CXXFLAGS"
export LDFLAGS="-fsanitize=thread"
python setup.py build --limited-api=no --qtpaths=<qt>/bin/qtpaths6 \
    --parallel=10 --build-tests --disable-pyi
```

`--disable-pyi` is not optional: the stub step imports the freshly built
modules into a plain interpreter, and an instrumented module refuses to
load there.

Check that the flags arrived rather than assuming it:

```
nm -u <builddir>/.../libshiboken6*.dylib | grep -c tsan
```

On macOS the runtime has to be present from process start, so preload it
and name the interpreter explicitly:

```
export DYLD_INSERT_LIBRARIES=$(dirname $(xcrun -f clang))/../lib/clang/*/lib/darwin/libclang_rt.tsan_osx_dynamic.dylib
export TSAN_OPTIONS="halt_on_error=0 abort_on_error=0 exitcode=0"
```

`abort_on_error` defaults to **1** on Darwin. Without turning it off the
run stops at the first report and every later one is invisible — the
counts then look smaller than they are.

## What a sanitizer cannot tell you on its own

Both sides have to be instrumented. With an uninstrumented libpython,
ThreadSanitizer cannot see the happens-before edges CPython establishes,
and every hand-off of an object between threads can look like a race. The
first pass here reported findings that disappeared once CPython itself was
built with `--with-thread-sanitizer`; they are listed as what they were.

Qt is not instrumented in any of these runs. A race inside Qt is
invisible; a race between our code and Qt shows up only on our side.
