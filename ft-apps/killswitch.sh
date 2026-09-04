#!/bin/bash
# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
#
# Does a scenario actually depend on the locks it is supposed to test?
#
#   ./killswitch.sh <build-dir> [rounds] [scenario ...]
#
# Runs each scenario three ways and counts the failures:
#
#   locks on,  GIL off    what we ship
#   locks off, GIL off    the kill switch - a scenario that proves a lock
#                         has to break here, and one that stays green
#                         proves nothing about that lock
#   locks on,  GIL on     the control - a failure here is not a
#                         free-threading bug at all
#
# The third column is the one that keeps us honest: dynamic_property
# crashed in all three, which is how it turned out to be an ordinary
# PySide bug (see tsan-befunde.md, Befund 5).
set -u

BD=${1:?usage: killswitch.sh <build-dir> [rounds] [scenario ...]}
shift
ROUNDS=${1:-5}
[ $# -gt 0 ] && shift

REPO=$(cd "$(dirname "$0")/.." && pwd)
. "$REPO/ft-apps/ft-env.sh"
BD=$(cd "$BD" && pwd)
W=$REPO/sources/pyside6/tests/manually/freethreading/stress.py

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
if [ "$got" != none ]; then
    echo "$BD is built with $got - this needs an uninstrumented tree" >&2
    exit 1
fi

SP=$(ls -d "$BD"/install/lib/python3.*/site-packages | head -1)
PY=${SANITIZE_PYTHON:-$HOME/.pyenv/versions/$FT_PYTHON_FT/bin/python3}

export DYLD_LIBRARY_PATH=$BD/install/lib:$BD/install/shiboken6:$BD/build/pyside6/libpyside:$BD/build/shiboken6/libshiboken
export PYTHONPATH=$SP
export BUILD_DIR=$BD/build

SCENARIOS=${*:-queued_signal move_to_thread container_convert dynamic_property virtual_override}

HOST=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
OUT=$REPO/ft-apps/sanitizer-runs/$(date +%m%d)-killswitch-$HOST
n=1
while [ -e "$OUT-$n" ]; do n=$((n + 1)); done
OUT=$OUT-$n
mkdir -p "$OUT"

{
  echo "build       $BD"
  echo "interpreter $PY"
  echo "rounds      $ROUNDS each"
  echo "started     $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  printf '%-22s %-14s %-14s %s\n' scenario "locks on" "locks OFF" "GIL on"
} | tee "$OUT/summary.txt"

for s in $SCENARIOS; do
    line=$(printf '%-22s' "$s")
    for cfg in "0b111 0" "0b000 0" "0b111 1"; do
        set -- $cfg
        opts=$1; gil=$2
        fails=0
        i=1
        while [ $i -le "$ROUNDS" ]; do
            PYSIDE6_OPTION_FT=$opts PYTHON_GIL=$gil \
                "$PY" "$W" "$s" > "$OUT/$s-$opts-gil$gil-$i.log" 2>&1 \
                || fails=$((fails + 1))
            i=$((i + 1))
        done
        line="$line $(printf '%-14s' "$fails/$ROUNDS")"
    done
    echo "$line" | tee -a "$OUT/summary.txt"
done

{
  echo
  echo "finished    $(date '+%Y-%m-%d %H:%M:%S')"
} | tee -a "$OUT/summary.txt"
echo "results in  $OUT"
