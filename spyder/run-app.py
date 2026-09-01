"""Start Spyder, report the GIL state, and shut down on a timer.

    venv-ft/bin/python run-app.py --conf-dir conf/manual --new-instance

Add PYTHON_GIL=0 to keep the GIL off; without it lxml switches it back on
during startup, see the README. Spyder redirects stdout into its internal
console unless --debug-info is given, so pass that when you want to read
the watchdog's verdict in the terminal.
"""
import os
import sys
import threading
import time

SECONDS = int(os.environ.get("SPY_RUNTIME", "45"))


def watchdog():
    time.sleep(SECONDS)
    print(f"gil after {SECONDS}s: {sys._is_gil_enabled()}", flush=True)
    print(f"threads alive: {threading.active_count()}", flush=True)
    for t in threading.enumerate():
        print(f"    {t.name}", flush=True)
    os._exit(0)


print("gil at start:", sys._is_gil_enabled(), flush=True)
threading.Thread(target=watchdog, daemon=True).start()

from spyder.app.start import main
main()
