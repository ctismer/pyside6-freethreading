#!/bin/bash
# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
#
# Run the free-threading stress scenarios under a sanitizer, and keep the
# result.
#
#   ./sanitize.sh tsan <build-dir> [scenario ...]
#   ./sanitize.sh asan <build-dir> [scenario ...]
#
# Nothing here is specific to one machine: the compiler is asked where its
# runtime lives, the interpreter is taken from the build tree, and macOS
# and Linux differ only in two variable names, handled below. Set
# SANITIZE_PYTHON to override the interpreter.
#
# The build directory has to be one built WITH that sanitizer:
#
#   CXXFLAGS="-fsanitize=thread -g -fno-omit-frame-pointer" \
#   CFLAGS="$CXXFLAGS" LDFLAGS="-fsanitize=thread" \
#   python setup.py build --debug --limited-api=no --disable-pyi ...
#
# CMake seeds its flags from the environment at the FIRST configure only, so
# this needs a build directory that does not exist yet. --disable-pyi
# because the stub step loads the freshly built, instrumented modules into
# an ordinary interpreter, and the runtime refuses that.
#
# Every run writes into a directory of its own, created empty. Nothing is
# ever written next to an older result: an evaluation that sums up leftovers
# reports yesterday's numbers as today's, which has happened.
set -u

usage() {
    echo "usage: sanitize.sh tsan|asan <build-dir> [scenario ...]" >&2
    exit 64
}
[ $# -ge 2 ] || usage
TOOL=$1
BD=$2
shift 2

REPO=$(cd "$(dirname "$0")/.." && pwd)
. "$REPO/ft-apps/ft-env.sh"
BD=$(cd "$BD" 2>/dev/null && pwd) || { echo "no such build dir" >&2; exit 1; }
WORKER=$REPO/sources/pyside6/tests/manually/freethreading/stress.py

# --- platform ---------------------------------------------------------------
# The sanitizer runtime has to be in the process before anything it must
# intercept; loading it with the extension module is too late and says
# "interceptors are not working".
case $(uname -s) in
  Darwin) PRELOAD_VAR=DYLD_INSERT_LIBRARIES
          LIBPATH_VAR=DYLD_LIBRARY_PATH
          RT_SUFFIX=_osx_dynamic.dylib ;;
  Linux)  PRELOAD_VAR=LD_PRELOAD
          LIBPATH_VAR=LD_LIBRARY_PATH
          RT_SUFFIX=-$(uname -m).so ;;
  *)      echo "unsupported platform: $(uname -s)" >&2; exit 1 ;;
esac

case $TOOL in
  tsan) OPTVAR=TSAN_OPTIONS
        MARKER="WARNING: ThreadSanitizer"
        # abort_on_error defaults to 1 on Darwin: without turning it off the
        # process dies at the first report and every later one is invisible.
        OPTS=${TSAN_OPTIONS:-"halt_on_error=0 abort_on_error=0 exitcode=0 history_size=4"} ;;
  asan) OPTVAR=ASAN_OPTIONS
        MARKER="ERROR: AddressSanitizer"
        # detect_leaks off: a free-threaded 3.15 has no pymalloc and mimalloc
        # pools, so leak reports here are about the allocator, not about us.
        OPTS=${ASAN_OPTIONS:-"halt_on_error=0 abort_on_error=0 detect_leaks=0"} ;;
  *)    usage ;;
esac

# Ask the compiler where its runtime is rather than guessing a path into an
# SDK: the answer is right for whichever clang built the tree.
CC=${CC:-clang}
RT=$($CC -print-file-name="libclang_rt.${TOOL}${RT_SUFFIX}" 2>/dev/null)
if [ ! -f "$RT" ]; then
    echo "no ${TOOL} runtime from $CC (asked for libclang_rt.${TOOL}${RT_SUFFIX})" >&2
    echo "set CC to the compiler that built $BD" >&2
    exit 1
fi

# What a tree is built with is asked of the tree, not assumed from where it
# sits. An asan-instrumented library in build/ once turned a whole
# kill-switch matrix into "5/5 everywhere in 2 seconds", which reads like a
# result and is not one.
tree_sanitizer() {
    lib=$(ls "$1"/build/shiboken6/libshiboken/libshiboken6*.dylib \
             "$1"/build/shiboken6/libshiboken/libshiboken6*.so 2>/dev/null | head -1)
    [ -n "$lib" ] || { echo unbuilt; return; }
    nm -u "$lib" 2>/dev/null | grep -q tsan && { echo tsan; return; }
    nm -u "$lib" 2>/dev/null | grep -q asan && { echo asan; return; }
    echo none
}

got=$(tree_sanitizer "$BD")
if [ "$got" != "$TOOL" ]; then
    echo "$BD is built with $got, not $TOOL" >&2
    echo "build it with ft-apps/build-sanitizer.sh $TOOL" >&2
    exit 1
fi

# --- interpreter ------------------------------------------------------------
# Taken from the tree, not guessed: a different interpreter looks for a
# different extension suffix and fails with a dlopen error that reads like a
# broken build.
SP=$(ls -d "$BD"/install/lib/python3.*/site-packages 2>/dev/null | head -1)
if [ -z "$SP" ]; then
    echo "no site-packages under $BD/install/lib - built with --skip-packaging?" >&2
    exit 1
fi
PYVER=$(basename "$(dirname "$SP")")            # python3.15t
# What the tree was built against, asked of the tree itself: the suffix of a
# built extension. Matching that is the only reliable test - an interpreter
# name says little, and pyenv calls a free-threaded 3.15 beta
# "3.15.0b3t-debug" while the tree calls it "python3.15t".
WANT=$(ls "$SP"/shiboken6/Shiboken*.so 2>/dev/null | head -1)
WANT=${WANT##*/Shiboken}                        # .cpython-315td-darwin.so

# The named interpreter for this tool comes first. Matching only on the
# extension suffix is not enough: 3.15.0b3t and the tsan build share the
# suffix .cpython-315t-darwin.so, so the search found the uninstrumented one
# and the whole run reported races inside CPython that are not there.
case $TOOL in
  tsan) NAMED=$FT_PYTHON_TSAN ;;
  asan) NAMED=$FT_PYTHON_ASAN ;;
esac
PY=${SANITIZE_PYTHON:-}
if [ -z "$PY" ]; then
    base=${PYVER#python}                        # 3.15t
    series=${base%t}                            # 3.15
    for cand in "$HOME/.pyenv/versions/$NAMED/bin/python3" \
                "$HOME/.pyenv/versions/$series"*t*/bin/python3 \
                "$HOME/.pyenv/versions/$series"*/bin/python3 \
                "$(command -v "$PYVER" 2>/dev/null)" \
                "$(command -v "python$series" 2>/dev/null)"; do
        [ -x "$cand" ] || continue
        got=$("$cand" -c 'import sysconfig
print(sysconfig.get_config_var("EXT_SUFFIX"))' 2>/dev/null)
        [ "$got" = "$WANT" ] && PY=$cand && break
    done
fi
if [ ! -x "${PY:-}" ]; then
    echo "no interpreter whose extension suffix is $WANT; set SANITIZE_PYTHON" >&2
    exit 1
fi

# And say so out loud rather than quietly producing nonsense. TSan against
# an uninstrumented libpython reports the interpreter, not us, and that is
# indistinguishable from a real finding in the log. ASan against one needs
# its runtime preloaded, which does not survive every way of starting
# python. An instrumented interpreter removes both problems.
case $TOOL in tsan) WANT_CFG=thread-sanitizer ;; asan) WANT_CFG=address-sanitizer ;; esac
WANT_CFG=$WANT_CFG "$PY" -c 'import os, sys, sysconfig
sys.exit(0 if os.environ["WANT_CFG"] in (sysconfig.get_config_var("CONFIG_ARGS") or "") else 1)' || {
    echo "$PY was not built --with-$WANT_CFG" >&2
    echo "build it with ft-apps/build-python.sh $TOOL" >&2
    exit 1
}

ALL_SCENARIOS="shared_delete call_vs_delete child_delete_vs_call signal_race
               lookup_vs_last_decref destroy_race lazy_converter shared_setter
               queued_signal move_to_thread container_convert dynamic_property
               virtual_override"
SCENARIOS=${*:-$ALL_SCENARIOS}

# A fresh, numbered directory per run. Never reused, never appended to.
# The host is part of the name because results from both machines end up
# in one place, and a bare 0904-tsan-1 from each is two directories that
# claim to be the same run. LocalHostName rather than `hostname -s`: over
# the network the latter answered with a DHCP UUID.
HOST=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
BASE=$REPO/ft-apps/sanitizer-runs
n=1
while [ -e "$BASE/$(date +%m%d)-$TOOL-$HOST-$n" ]; do n=$((n + 1)); done
OUT=$BASE/$(date +%m%d)-$TOOL-$HOST-$n
mkdir -p "$OUT"

export "$PRELOAD_VAR=$RT"
export "$LIBPATH_VAR=$BD/install/lib:$BD/install/shiboken6:$BD/build/pyside6/libpyside:$BD/build/shiboken6/libshiboken"
# The sanitizer options go into the environment here rather than through
# `env VAR=... python`: on macOS /usr/bin/env is SIP-protected and strips
# every DYLD_* variable from what it starts, which takes the runtime and the
# library path with it. The failure looks like a broken build - a dlopen
# that cannot find libshiboken6 - and has nothing to do with the build.
export "$OPTVAR=$OPTS"
export PYTHONPATH=$SP
# stress.py calls init_paths(), which without BUILD_DIR takes the newest
# build_history entry - whatever was built last, on any machine, with any
# sanitizer. That is how a run against one tree silently loads another and
# reports "interceptors are not working".
export BUILD_DIR=$BD/build
export PYTHON_GIL=0
export PYSIDE6_OPTION_FT=${PYSIDE6_OPTION_FT:-0b111}

SUMMARY=$OUT/summary.txt
{
  echo "tool        $TOOL"
  echo "host        $(uname -s) $(uname -m), $HOST"
  echo "build       $BD"
  echo "interpreter $PY"
  echo "runtime     $RT"
  echo "options     $OPTS"
  echo "locks       PYSIDE6_OPTION_FT=$PYSIDE6_OPTION_FT"
  echo "threads     ${STRESS_THREADS:-8}, iters ${STRESS_ITERS:-6000}"
  echo "started     $(date '+%Y-%m-%d %H:%M:%S')"
  echo
} | tee "$SUMMARY"

# Smoke first. Without it a failing import looks like every scenario
# passing with nothing to report.
if ! "$PY" -c "
from PySide6.QtCore import QObject
QObject().setObjectName('x')
print('smoke ok')
" > "$OUT/smoke.log" 2>&1; then
    echo "SMOKE FAILED - see $OUT/smoke.log" | tee -a "$SUMMARY"
    tail -5 "$OUT/smoke.log" | tee -a "$SUMMARY"
    exit 1
fi

for s in $SCENARIOS; do
    start=$(date +%s)
    "$PY" "$WORKER" "$s" > "$OUT/$s.log" 2>&1
    rc=$?
    reports=$(grep -c "$MARKER" "$OUT/$s.log")
    where=$(grep -A3 "$MARKER" "$OUT/$s.log" \
            | grep -oE '[A-Za-z_]+\.cpp:[0-9]+' | sort -u | tr '\n' ' ')
    printf '%-22s rc %-4s reports %-4s %3ss  %s\n' \
           "$s" "$rc" "$reports" "$(( $(date +%s) - start ))" "$where" \
        | tee -a "$SUMMARY"
done

{
  echo
  echo "finished    $(date '+%Y-%m-%d %H:%M:%S')"
} | tee -a "$SUMMARY"
echo "results in  $OUT"
