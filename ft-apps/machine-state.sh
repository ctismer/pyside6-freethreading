#!/bin/bash
# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
#
# Report everything about this machine that a run depends on, in a form two
# machines can be diffed with.
#
#   ./machine-state.sh                     # this machine
#   ssh other ...ft-apps/machine-state.sh  # the other one
#   diff <(./machine-state.sh) <(ssh amrumer.local '.../machine-state.sh')
#
# The machines are meant to be interchangeable: the same command has to mean
# the same thing on either. Anything this prints differently is a reason a
# result cannot be compared, and the diff is the checklist.
set -u
cd "$(dirname "$0")/.." || exit 1

. "$(pwd)/ft-apps/ft-env.sh"

# Only the interpreters the runs actually use - ft-env.sh names them. The
# pyenv directory holds years of old ones; listing them all buries the
# difference that matters.
NEEDED=$FT_PYTHONS

echo "== interpreters (the ones runs use)"
for v in $NEEDED; do
    if [ -x "$HOME/.pyenv/versions/$v/bin/python3" ]; then
        printf '%-20s %s\n' "$v" "$("$HOME/.pyenv/versions/$v/bin/python3" -c \
            'import sys,sysconfig
gil = "free-threaded" if not sys._is_gil_enabled() else "gil"
dbg = "debug" if sysconfig.get_config_var("Py_DEBUG") else ""
san = "tsan" if "thread-sanitizer" in (sysconfig.get_config_var("CONFIG_ARGS") or "") else ""
print(" ".join(x for x in (gil, dbg, san) if x))' 2>/dev/null)"
    else
        printf '%-20s MISSING\n' "$v"
    fi
done

echo
echo "== qt"
for q in "$HOME"/Qt-*/bin/qtpaths6; do
    [ -x "$q" ] && echo "$(echo "$q" | sed "s|$HOME/||")  $("$q" --qt-version 2>/dev/null)"
done

echo
echo "== tools"
for t in cmake ninja clang git; do
    printf '%-8s %s\n' "$t" "$($t --version 2>/dev/null | head -1)"
done
printf '%-8s %s\n' libclang "$([ -d "${CLANG_INSTALL_DIR:-$HOME/libclang}" ] && echo present || echo MISSING)"

echo
echo "== repo"
br=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
[ "$br" = "$FT_BRANCH" ] || br="$br  (expected $FT_BRANCH)"
echo "branch $br"
echo "head   $(git rev-parse --short HEAD 2>/dev/null) $(git log -1 --format=%s 2>/dev/null | cut -c1-50)"
echo "dirty  $(git status --porcelain 2>/dev/null | grep -cv '^??') tracked, $(git status --porcelain 2>/dev/null | grep -c '^??') untracked"

echo
echo "== build roots"
for d in build build-tsan build-asan; do
    if [ -d "$d" ]; then
        for tree in "$d"/*/; do
            [ -d "$tree/build" ] || continue
            lib=$(ls "$tree"/build/shiboken6/libshiboken/libshiboken6*.dylib \
                     "$tree"/build/shiboken6/libshiboken/libshiboken6*.so 2>/dev/null | head -1)
            san=none
            if [ -n "$lib" ]; then
                nm -u "$lib" 2>/dev/null | grep -q tsan && san=tsan
                nm -u "$lib" 2>/dev/null | grep -q asan && san=asan
            fi
            echo "$(echo "$tree" | sed 's|/$||')  sanitizer=$san"
        done
    else
        echo "$d  MISSING"
    fi
done

echo
echo "== ft tools"
for f in ft-apps/ft-env.sh ft-apps/sanitize.sh ft-apps/build-sanitizer.sh \
         ft-apps/build-python.sh ft-apps/killswitch.sh \
         ft-apps/machine-state.sh ft-apps/feature_race.py ft-apps/dict_race.py \
         ft-apps/property_qobject_crash.py check-accept.py check-chain.sh check-builds.sh; do
    if [ -f "$f" ]; then
        # A checksum, so a tool that differs shows up even when both exist.
        printf '%-32s %s\n' "$f" "$(cksum < "$f" | awk '{print $1}')"
    else
        printf '%-32s MISSING\n' "$f"
    fi
done

echo
echo "== app venvs"
for v in ft-apps/napari/venv ft-apps/spyder/venv*; do
    if [ -d "$v" ]; then
        ver=$("$v/bin/python" -c 'import PySide6; print(PySide6.__version__)' 2>/dev/null)
        echo "$v  PySide6 ${ver:-none}"
    else
        echo "$v  MISSING"
    fi
done
