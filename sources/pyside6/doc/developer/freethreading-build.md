# Building PySide6 for a free-threaded interpreter

There are no free-threaded PySide6 wheels. To run an application against
this branch, build them. The procedure is the documented one in
`doc/building_from_source/`; this note only records what differs.

## The interpreter

A free-threaded CPython, and **not** a debug build - a wheel built against
a debug interpreter loads only in that interpreter. Verify:

```
python -c "import sysconfig; print(sysconfig.get_config_var('Py_GIL_DISABLED'))"
```

must print `1`.

## The limited API must be off

`--limited-api=no` is not optional. With it on, the build defines
`Py_LIMITED_API`, and `Python.h` refuses:

```c
// gh-111506: The free-threaded build is not compatible with the limited API
// or the stable ABI.
#if defined(Py_LIMITED_API) && defined(Py_GIL_DISABLED)
#  error "The limited API is not currently supported in the free-threaded build"
#endif
```

The build fails before it compiles anything. PEP 803 is the proposal to
lift this; until it lands, free threading and the stable ABI exclude each
other.

## Build and wheels

```
python setup.py build --limited-api=no --qtpaths=<qt>/bin/qtpaths6 \
    --module-subset=Core,Gui,Widgets,Network,OpenGL,OpenGLWidgets,Svg,SvgWidgets,Test,PrintSupport,Concurrent,Xml \
    --parallel=10 --skip-docs
python create_wheels.py --build-dir=build/<build-dir-name> --no-examples
pip install dist/*.whl
```

The module subset is a Qt widget application plus `QtTest`, which
`pytest-qt` needs; drop it to build everything.

Add `--standalone` for a wheel that carries Qt with it and runs on a
machine that has none. On macOS that logs a long row of "Can only create
symlinks within the same directory" - those are the convenience symlinks
at the top of each framework, not the libraries, and the result works:
check it by installing into a fresh environment and asking

```
python -c "from PySide6.QtCore import QLibraryInfo as q; \
    print(q.path(q.LibraryPath.LibrariesPath))"
```

which must answer inside site-packages, not from the Qt installation the
wheel was built against.

## Running an application against it

Install the wheels first, then the application **without** its Qt extra.
The extra names a released PyQt or PySide, which pip then fetches from the
index alongside the binding that is already installed. The version built
here is a pre-release (`6.12.0a1`), which pip would not pick anyway.

Applications that use `qtpy` choose their binding from the environment.
Make it explicit:

```
export QT_API=pyside6
```
