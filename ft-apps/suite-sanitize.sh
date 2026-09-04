#!/bin/bash
# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
#
# Run the pyside6 test suite under a sanitizer.
#
#   ./suite-sanitize.sh tsan [testrunner args ...]
#   ./suite-sanitize.sh asan [testrunner args ...]
#
# testrunner.py rather than raw ctest: that is what an acceptance run uses,
# and a sanitizer finding in a test nobody runs is not worth much. The tree
# is picked with --build, not by "the newest build" - with three build roots
# around, the default would take whichever was compiled last.
#
# The scenarios in sanitize.sh are eight lines of code hammering one spot;
# the suite is thousands of lines doing ordinary things. Both are needed:
# Befund 4 came out of the suite and out of no scenario.
set -u

TOOL=${1:?usage: suite-sanitize.sh tsan|asan [testrunner args ...]}
shift

REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"
. "$REPO/ft-apps/ft-env.sh"

case $TOOL in
  tsan) MARKER="WARNING: ThreadSanitizer"
        OPTVAR=TSAN_OPTIONS
        OPTS=${TSAN_OPTIONS:-"halt_on_error=0 abort_on_error=0 exitcode=0 history_size=4"}
        PY=$HOME/.pyenv/versions/$FT_PYTHON_TSAN/bin/python3 ;;
  asan) MARKER="ERROR: AddressSanitizer"
        OPTVAR=ASAN_OPTIONS
        OPTS=${ASAN_OPTIONS:-"halt_on_error=0 abort_on_error=0 detect_leaks=0"}
        PY=$HOME/.pyenv/versions/$FT_PYTHON_ASAN/bin/python3 ;;
  *)    echo "usage: suite-sanitize.sh tsan|asan" >&2; exit 64 ;;
esac

BD=$(ls -d "$REPO"/build-$TOOL/*/ 2>/dev/null | head -1)
[ -n "$BD" ] || { echo "no build-$TOOL tree; run build-sanitizer.sh $TOOL" >&2; exit 1; }
BD=${BD%/}

case $(uname -s) in
  Darwin) PRELOAD_VAR=DYLD_INSERT_LIBRARIES; LIBPATH_VAR=DYLD_LIBRARY_PATH
          RT_SUFFIX=_osx_dynamic.dylib ;;
  Linux)  PRELOAD_VAR=LD_PRELOAD; LIBPATH_VAR=LD_LIBRARY_PATH
          RT_SUFFIX=-$(uname -m).so ;;
esac
# Preloaded anyway: it is what an uninstrumented process would need, and it
# is harmless next to an instrumented interpreter. What carries the run is
# the interpreter - the variable does not survive the way through ctest.
RT=$(${CC:-clang} -print-file-name="libclang_rt.${TOOL}${RT_SUFFIX}")
[ -f "$RT" ] || { echo "no $TOOL runtime" >&2; exit 1; }

HOST=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
OUT=$REPO/ft-apps/sanitizer-runs/$(date +%m%d)-suite-$TOOL-$HOST
n=1
while [ -e "$OUT-$n" ]; do n=$((n + 1)); done
OUT=$OUT-$n
mkdir -p "$OUT"

export "$PRELOAD_VAR=$RT"
export "$LIBPATH_VAR=$BD/install/lib:$BD/install/shiboken6:$BD/build/pyside6/libpyside:$BD/build/shiboken6/libshiboken"
export "$OPTVAR=$OPTS"
export PYTHON_GIL=0
export PYSIDE6_OPTION_FT=${PYSIDE6_OPTION_FT:-0b111}

{
  echo "tool        $TOOL (suite)"
  echo "host        $(uname -s) $(uname -m), $HOST"
  echo "build       $BD"
  echo "interpreter $PY"
  echo "options     $OPTS"
  echo "locks       PYSIDE6_OPTION_FT=$PYSIDE6_OPTION_FT"
  echo "started     $(date '+%Y-%m-%d %H:%M:%S')"
} | tee "$OUT/summary.txt"

# testrunner kills ctest after PYSIDE_TEST_TIMEOUT seconds per project and
# still exits 0. Under a sanitizer everything runs about ten times slower,
# so the default 20 minutes lose the second half of the suite - that is
# what the "Suite-Abbruch bei Test 201" turned out to be. Two hours here.
export PYSIDE_TEST_TIMEOUT=${PYSIDE_TEST_TIMEOUT:-7200}

"$PY" testrunner.py test --build "build-$TOOL" "$@" > "$OUT/suite.log" 2>&1
rc=$?

# Say it out loud. A partial run with no findings looks exactly like a
# clean one in the summary, and that is worse than no run at all.
partial=$(grep -c "aborted, partial result" "$OUT/suite.log")

{
  echo
  echo "testrunner rc $rc"
  if [ "$partial" -gt 0 ]; then
      echo "INCOMPLETE  $partial project(s) hit PYSIDE_TEST_TIMEOUT"
      echo "            last test: $(grep -E "Test +#[0-9]+:" "$OUT/suite.log" | tail -1 | sed -E "s/.*Test +#//; s/ .*//")"
      echo "            the numbers below cover only what ran"
  fi
  echo "reports       $(grep -c "$MARKER" "$OUT/suite.log")"
  echo
  echo "where:"
  grep -A3 "$MARKER" "$OUT/suite.log" \
    | grep -oE '[A-Za-z_]+\.cpp:[0-9]+' | sort | uniq -c | sort -rn | head -20
  echo
  echo "tests that did not pass:"
  # ctest writes "***Failed" / "***Timeout" / "***Exception"; testrunner
  # prefixes every line with "RUN n: ". Counting the distinct test names
  # rather than the lines, because a failing test is repeated by the reruns.
  grep -E "\*\*\*(Failed|Timeout|Exception)" "$OUT/suite.log" \
    | sed -E 's/.*Test +#[0-9]+: +//; s/ *\.+\*\*\*.*//' \
    | sort -u
  echo
  echo "finished    $(date '+%Y-%m-%d %H:%M:%S')"
} | tee -a "$OUT/summary.txt"
echo "results in  $OUT"
