# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
#
# The one place that says what a free-threading run needs. Sourced, not run:
#
#   . "$(dirname "$0")/ft-env.sh"
#
# Two machines are only interchangeable if the same command means the same
# thing on either, and that only holds while a single file decides which
# interpreter, which Qt and which build root is meant. Every name below was
# a difference between the machines at some point.

# pyenv names. Not globbed: the glob that used to pick the tsan interpreter
# sorted 3.15t-dev-debug last and took that instead.
FT_PYTHON_FT=${FT_PYTHON_FT:-3.15.0b3t-debug}      # free-threaded debug, the workhorse
FT_PYTHON_TSAN=${FT_PYTHON_TSAN:-3.15.0b4t-tsan}   # libpython --with-thread-sanitizer
FT_PYTHON_ASAN=${FT_PYTHON_ASAN:-3.15.0b4t-asan}   # libpython --with-address-sanitizer
FT_PYTHON_GIL=${FT_PYTHON_GIL:-3.14.3}             # the control column
FT_PYTHONS="$FT_PYTHON_FT $FT_PYTHON_TSAN $FT_PYTHON_ASAN $FT_PYTHON_GIL 3.14.3t 3.12.11"

FT_QTPATHS=${QTPATHS:-$HOME/Qt-6.12/bin/qtpaths6}
FT_BRANCH=${FT_BRANCH:-phase1-lease-owner}

# Homebrew and MacPorts are not in a login PATH, and a non-interactive ssh
# gets a login PATH. Without this cmake and ninja look missing on the remote
# machine only - and setup.py reports that as a TypeError about NoneType.
# CMake.app is where the macOS installer puts cmake AND ctest; one machine
# has it there and the other has Homebrew's. Without this, ctest is simply
# not found on one of the two.
for _d in /opt/homebrew/bin /usr/local/bin /opt/local/bin \
          /Applications/CMake.app/Contents/bin; do
    case ":$PATH:" in *":$_d:"*) ;; *) [ -d "$_d" ] && PATH="$_d:$PATH" ;; esac
done
unset _d
export PATH
