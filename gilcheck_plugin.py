"""Record whether the GIL was really disabled for the whole test session.

A module that does not declare free-threading support switches the GIL back
on at import time, and it never goes off again - so the state at session
finish is the state that held from that point on. Checking it at the end is
therefore the honest question: was this run free-threaded or not?
"""
import sys


def pytest_configure(config):
    config._gil_at_start = sys._is_gil_enabled()


def pytest_sessionfinish(session, exitstatus):
    start = getattr(session.config, "_gil_at_start", None)
    end = sys._is_gil_enabled()
    print(f"\n[gilcheck] GIL at session start: {start}")
    print(f"[gilcheck] GIL at session end  : {end}")
    if end:
        print("[gilcheck] VERDICT: this run was NOT free-threaded")
    else:
        print("[gilcheck] VERDICT: free-threaded throughout")
