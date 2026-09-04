#!/bin/bash
# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
#
# Build PySide with a sanitizer, into a root of its own.
#
#   ./build-sanitizer.sh tsan [extra setup.py args ...]
#   ./build-sanitizer.sh asan [extra setup.py args ...]
#   ./build-sanitizer.sh none [extra setup.py args ...]
#
# "none" builds the same tree without instrumentation, into build/. That is
# the control the kill-switch matrix runs on, and it has to differ from the
# other two in nothing but the sanitizer flags - otherwise a difference in
# the result says nothing about the locks.
#
# Each sanitizer gets its own build root - build-tsan/, build-asan/ - next
# to the ordinary build/. Three reasons, all learned the hard way:
#
#   * CMake seeds CMAKE_CXX_FLAGS from the environment at the FIRST
#     configure only. A sanitizer build therefore needs a directory that
#     does not exist yet, and reusing the ordinary one means wiping it.
#   * Renaming a build directory afterwards does not work: the @rpath
#     entries in the libraries are absolute, so the renamed tree keeps
#     loading whatever now sits under the old name. That produces
#     "interceptors are not working" from a tree that is not instrumented
#     at all, and it costs an hour to see.
#   * The same layout on every machine means a command that works here
#     works there. No thinking about which tree is which.
#
# The interpreter is passed as SANITIZE_PYTHON, or defaults to the newest
# free-threaded debug build under pyenv.
set -eu

TOOL=${1:?usage: build-sanitizer.sh tsan|asan [setup.py args ...]}
shift

# The flag is not named like the tool: -fsanitize=thread / =address, while
# the runtime library and the option variable are tsan / asan.
case $TOOL in
  tsan) FLAG=thread ;;
  asan) FLAG=address ;;
  none) FLAG= ;;
  *) echo "unknown sanitizer: $TOOL" >&2; exit 64 ;;
esac

REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"
. "$REPO/ft-apps/ft-env.sh"

# The two sanitizers do not want the same interpreter, and the choice is not
# a detail: without a libpython built --with-thread-sanitizer TSan cannot see
# CPython's own happens-before edges and reports races that are not there.
# ASan has no such requirement and uses the ordinary free-threaded build.
# Named, not globbed: glob order picked 3.15t-dev-debug over 3.15.0b4t-tsan.
# The interpreter is baked into the tree: ctest starts the tests with the
# python CMake was configured with, not with whatever runs testrunner. A
# suite run under a sanitizer therefore needs the instrumented interpreter
# here, at build time - setting it later changes nothing.
case $TOOL in
  tsan) DEFAULT_PY=$FT_PYTHON_TSAN ;;
  asan) DEFAULT_PY=$FT_PYTHON_ASAN ;;
  *)    DEFAULT_PY=$FT_PYTHON_FT ;;
esac
PY=${SANITIZE_PYTHON:-$HOME/.pyenv/versions/$DEFAULT_PY/bin/python3}
[ -x "${PY:-}" ] || { echo "no interpreter at $PY; set SANITIZE_PYTHON" >&2; exit 1; }

# setup.py calls which("cmake") and hands the result to Path() without
# checking, so a missing cmake arrives as a TypeError about NoneType rather
# than as "cmake not found" (ft-env.sh has already fixed up PATH).
for tool in cmake ninja; do
    command -v $tool > /dev/null || { echo "no $tool in PATH" >&2; exit 1; }
done

QTPATHS=$FT_QTPATHS
[ -x "$QTPATHS" ] || { echo "no qtpaths at $QTPATHS; set QTPATHS" >&2; exit 1; }

if [ -n "$FLAG" ]; then
    BASE=$REPO/build-$TOOL
    export CXXFLAGS="-fsanitize=$FLAG -g -fno-omit-frame-pointer"
    export LDFLAGS="-fsanitize=$FLAG"
else
    BASE=$REPO/build
    export CXXFLAGS="-g -fno-omit-frame-pointer"
    export LDFLAGS=
fi
export CFLAGS="$CXXFLAGS"
export CLANG_INSTALL_DIR=${CLANG_INSTALL_DIR:-$HOME/libclang}

echo "sanitizer   $TOOL"
echo "interpreter $PY"
echo "build base  $BASE"
echo "flags       $CXXFLAGS"
echo "python      $("$PY" -c 'import sys; print(sys.version.split()[0])')"

# --disable-pyi: the stub step imports the freshly built, instrumented
# modules with an ordinary interpreter, and the runtime refuses that
# ("interceptors are not working"). The stubs are of no use here anyway.
"$PY" setup.py build \
    --build-base="$BASE" \
    --debug --limited-api=no --qtpaths="$QTPATHS" \
    --parallel="${BUILD_PARALLEL:-10}" --skip-docs --no-qt-tools \
    --build-tests --disable-pyi "$@"

# Newest, not first: build/ can hold older trees whose name sorts ahead of
# the one just built, and naming the wrong one sends the next run at it.
tree=$(ls -dt "$BASE"/*/ 2>/dev/null | head -1)
echo
echo "built into  $tree"
echo "run it with ft-apps/sanitize.sh $TOOL $tree"
