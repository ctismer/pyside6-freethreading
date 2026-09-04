#!/bin/bash
# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
#
# Build one of the interpreters a free-threading run needs, into pyenv.
#
#   ./build-python.sh tsan     # free-threaded, --with-thread-sanitizer
#   ./build-python.sh asan     # free-threaded debug, --with-address-sanitizer
#   ./build-python.sh ft       # free-threaded debug, the workhorse
#
# Why this exists rather than a line in a README: TSan only sees CPython's
# own happens-before edges when libpython itself is instrumented. Run against
# an ordinary interpreter it reports races inside the interpreter that are
# not races, and one machine having the instrumented build while the other
# does not makes the two machines report different things about the same
# code.
#
# The version definitions live next to this script instead of being taken
# from whatever pyenv happens to be installed: `brew upgrade pyenv` replaces
# the definition directory, and 3.15.0b4 disappeared from it that way while
# one machine still had it. python-build takes a path, so the definition
# in the repo is the one both machines use.
set -eu

WHAT=${1:?usage: build-python.sh tsan|ft}
REPO=$(cd "$(dirname "$0")/.." && pwd)
. "$REPO/ft-apps/ft-env.sh"

DEFS=$REPO/ft-apps/python-build-defs

case $WHAT in
  tsan) NAME=$FT_PYTHON_TSAN
        DEF=$DEFS/3.15.0b4t
        OPTS="--disable-gil --with-thread-sanitizer --enable-shared" ;;
  # ASan needs an instrumented interpreter for a different reason than TSan:
  # preloading its runtime works when python is started directly, but the
  # test suite goes through ctest and the variable does not survive the way
  # there - every test then dies with "Interceptors are not working". An
  # instrumented interpreter needs no preloading at all.
  # --with-pydebug so the extension suffix stays .cpython-315td-darwin.so
  # and the existing build-asan/ tree loads against it unchanged.
  asan) NAME=$FT_PYTHON_ASAN
        DEF=$DEFS/3.15.0b4t
        OPTS="--disable-gil --with-pydebug --with-address-sanitizer --enable-shared" ;;
  ft)   NAME=$FT_PYTHON_FT
        DEF=$DEFS/3.15.0b3t
        OPTS="--disable-gil --with-pydebug --enable-shared" ;;
  *)    echo "unknown: $WHAT" >&2; exit 64 ;;
esac

[ -f "$DEF" ] || { echo "no definition $DEF" >&2; exit 1; }
command -v python-build > /dev/null || { echo "no python-build in PATH" >&2; exit 1; }

PREFIX=$HOME/.pyenv/versions/$NAME
if [ -d "$PREFIX" ]; then
    echo "$PREFIX exists - remove it first if you mean to rebuild"
    exit 0
fi

echo "definition $DEF"
echo "prefix     $PREFIX"
echo "options    $OPTS"

# -O1 with frame pointers: the sanitizer needs the frames to name a stack,
# and -O0 makes an already slow run useless.
export PYTHON_CONFIGURE_OPTS="$OPTS"
export PYTHON_CFLAGS="-g -O1 -fno-omit-frame-pointer"
python-build "$DEF" "$PREFIX"

# setup.py imports packaging before it does anything else, and a freshly
# built interpreter has none of it. Without this the first PySide build
# against a new interpreter dies with ModuleNotFoundError after the whole
# CPython build has already run.
"$PREFIX/bin/python3" -m pip install --upgrade pip setuptools packaging

"$PREFIX/bin/python3" -c 'import sys, sysconfig
print("gil enabled:", sys._is_gil_enabled())
print("config     :", sysconfig.get_config_var("CONFIG_ARGS")[:120])'
