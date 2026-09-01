#!/bin/bash
# Build one of the environments this directory measures against.
#
#   ./setup-venvs.sh ft     3.14.3t + our free-threaded wheels
#   ./setup-venvs.sh twin   3.14.3  + our wheels built for a GIL interpreter
#   ./setup-venvs.sh pypi   3.12    + PySide6 from PyPI
#
# "twin" is the one that answers the real question. It is the same PySide6
# source built against the same Qt for the same Python version, and only
# the GIL differs - so a difference between venv-ft and venv-twin cannot be
# blamed on a Qt version, a PySide6 version or a Python version. venv-pypi
# mixes all three and is only a sanity check.
#
# Spyder comes from a git checkout in every case, so the application code
# is identical and only the binding underneath moves.
set -e
HERE=$(cd $(dirname $0); pwd)
ROOT=$HERE/../..
WHAT=${1:?usage: setup-venvs.sh ft|twin|pypi}
SPYDER=${SPYDER:-$HOME/src/spyder}
KERNELS=${KERNELS:-$HOME/src/spyder-kernels}

# Spyder's setup.py picks its Qt binding from this variable. "conda-forge"
# is the one value that pulls in no binding at all, which is what we want:
# the binding is already installed, and PyPI has no free-threaded PySide6.
export SPYDER_QT_BINDING=conda-forge

TEST_EXTRAS="coverage cython flaky matplotlib pandas pillow pytest<8.0 \
    pytest-cov pytest-lazy-fixture pytest-mock pytest-order pytest-qt \
    pytest-timeout pyyaml scipy sympy"
# applaunchservices still imports distutils, which 3.12 removed.
EXTRA="setuptools"

case $WHAT in
ft)
    VENV=$HERE/venv-ft
    PYTHON=${FT_PYTHON:-$HOME/.pyenv/versions/3.14.3t/bin/python3}
    WHEELS="$ROOT/dist/shiboken6-*-cp314-cp314t-*.whl
            $ROOT/dist/pyside6_essentials-*-cp314-cp314t-*.whl
            $ROOT/dist/pyside6_addons-*-cp314-cp314t-*.whl
            $ROOT/dist/pyside6-*-cp314-cp314t-*.whl" ;;
twin)
    VENV=$HERE/venv-twin
    PYTHON=${TWIN_PYTHON:-$HOME/.pyenv/versions/3.14.3/bin/python3}
    WHEELS="$ROOT/dist/shiboken6-*-cp314-cp314-*.whl
            $ROOT/dist/pyside6_essentials-*-cp314-cp314-*.whl
            $ROOT/dist/pyside6_addons-*-cp314-cp314-*.whl
            $ROOT/dist/pyside6-*-cp314-cp314-*.whl" ;;
pypi)
    VENV=$HERE/venv-pypi
    PYTHON=${GIL_PYTHON:-$HOME/.pyenv/versions/3.12.11/bin/python3}
    WHEELS="pyside6" ;;
*)  echo "unknown environment: $WHAT"; exit 1 ;;
esac

rm -r $VENV 2>/dev/null || true
$PYTHON -m venv $VENV
$VENV/bin/pip install -q --upgrade pip
$VENV/bin/pip install -q $WHEELS
$VENV/bin/pip install -q -e $SPYDER
$VENV/bin/pip install -q -e $KERNELS
$VENV/bin/pip install -q $TEST_EXTRAS $EXTRA
$VENV/bin/python -c "
import sys
from PySide6 import QtCore
gil = getattr(sys, '_is_gil_enabled', lambda: True)()
print(f'$(basename $VENV): python {sys.version.split()[0]}'
      f'  PySide6 {QtCore.__version__}  Qt {QtCore.qVersion()}  GIL {gil}')"
