# Copyright (C) 2026 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0
from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
import unittest

from pathlib import Path
sys.path.append(os.fspath(Path(__file__).resolve().parents[1]))
from init_paths import init_test_paths
init_test_paths(False)

import PySide6


# The build, not the interpreter: "import PySide6" may have turned the GIL on
@unittest.skipUnless(sysconfig.get_config_var("Py_GIL_DISABLED"), "free-threaded builds only")
class AllModulesGilTest(unittest.TestCase):
    def testNoModuleTurnsTheGilBackOn(self):
        """Test that importing every module keeps the GIL off."""
        # A fresh process starts with the GIL off, whatever this one imported
        proc = subprocess.run([sys.executable, __file__, "--check-gil"],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


def _check_gil_stays_off():
    """Import every module, report the first that turns the GIL on."""
    if sys._is_gil_enabled():
        print("importing PySide6 (shiboken6) re-enabled the GIL")
        return 1
    # QtQmlFeatures declares Py_MOD_GIL_USED by hand. It is not generated, so
    # the generator option does not reach it; left to its authors to decide.
    for name in (n for n in PySide6.__all__ if n != "QtQmlFeatures"):
        try:
            exec(f"import PySide6.{name}")
        except ImportError:
            continue  # module not built
        if sys._is_gil_enabled():
            print(f"importing PySide6.{name} re-enabled the GIL")
            return 1
    return 0


if __name__ == '__main__':
    if "--check-gil" in sys.argv:
        sys.exit(_check_gil_stays_off())
    unittest.main()
