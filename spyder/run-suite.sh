#!/bin/bash
# Run Spyder's test suite, one pytest process per test FILE.
#
#   ./run-suite.sh ft-gil1  venv-ft/bin/python   1
#   ./run-suite.sh ft-gil0  venv-ft/bin/python   0
#   ./run-suite.sh gilref   venv-gil/bin/python  1
#
# Per file, not per directory, for two reasons. A crash - and Spyder has
# several that a GIL build shares - then costs one file instead of every
# test behind it, so the columns stay aligned and can be compared test by
# test. And windows left standing by an earlier file stop stealing focus
# from the next one: run as a directory, sixteen keyboard-shortcut tests
# fail that pass when the file runs alone.
#
# The price is a fresh interpreter per file, about four seconds each.
#
# spyder/app/tests is left out: its conftest imports QtWebEngineWidgets
# unconditionally and our Qt has no WebEngine.
HERE=$(cd $(dirname $0); pwd)
TAG=$1
PY=$2
GIL=$3
SPYDER=${SPYDER:-$HOME/src/spyder}
OUT=$HERE/logs/$TAG
CONF=$HERE/conf/$TAG
mkdir -p $OUT
export PYTHON_GIL=$GIL
export SPYDER_PYTEST=True
export QT_API=pyside6
cd $SPYDER
for f in $(find spyder -path spyder/app/tests -prune -o \
                       -type f -name "test_*.py" -print | sort); do
    name=$(echo ${f%.py} | tr '/' '.')
    export SPYDER_CONFDIR=$CONF
    rm -r $CONF 2>/dev/null
    mkdir -p $CONF
    $PY -m pytest $f \
        --continue-on-collection-errors \
        -q -rw -s -W ignore::UserWarning \
        --timeout=120 --timeout-method=thread \
        -p no:cacheprovider \
        --junitxml=$OUT/$name.xml > $OUT/$name.log 2>&1
    rc=$?
    echo "$rc  $name  $(tail -3 $OUT/$name.log | grep -E 'passed|failed|error|no tests' | tail -1)"
done
