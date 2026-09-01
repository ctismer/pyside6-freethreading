"""A/B the napari stress driver: with the binding locks, and without.

Each run is its own process, because a crash is the result we are looking
for. Reports how many of REPEATS runs survived in each column.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The interpreter that has the free-threaded wheels installed. Defaults to
# the one running this script, which is usually right.
PY = Path(os.environ.get("FT_PYTHON", sys.executable))
DRIVER = HERE / "napari_stress.py"
REPEATS = int(os.environ.get("REPEATS", "10"))
TIMEOUT = int(os.environ.get("TIMEOUT", "180"))

COLUMNS = [
    ("GIL on            ", {"PYTHON_GIL": "1"}),
    ("FT, locks on      ", {"PYTHON_GIL": "0"}),
    ("FT, locks off     ", {"PYTHON_GIL": "0", "PYSIDE6_OPTION_FT": "off"}),
]


def run_once(extra):
    env = dict(os.environ, QT_API="pyside6", **extra)
    try:
        p = subprocess.run([str(PY), str(DRIVER)], env=env, timeout=TIMEOUT,
                           capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    if p.returncode != 0:
        tail = (p.stderr or p.stdout).strip().splitlines()
        return "crash", tail[-1] if tail else f"rc={p.returncode}"
    return "ok", (p.stdout or "").strip().splitlines()[-1]


print(f"repeats={REPEATS} timeout={TIMEOUT}s "
      f"workers={os.environ.get('STRESS_WORKERS', '8')} "
      f"yields={os.environ.get('STRESS_YIELDS', '60')} "
      f"churn={os.environ.get('STRESS_CHURN', '300')}\n")

for name, extra in COLUMNS:
    bad, last, reasons = 0, "", {}
    for _ in range(REPEATS):
        status, detail = run_once(extra)
        if status == "ok":
            last = detail
        else:
            bad += 1
            reasons[detail[:90]] = reasons.get(detail[:90], 0) + 1
    verdict = "ok" if bad == 0 else f"{bad}BAD"
    print(f"{name} {verdict:>8}/{REPEATS}   {last}")
    for r, n in reasons.items():
        print(f"       {n}x {r}")
