"""Report which imports re-enable the GIL on a free-threaded interpreter.

Each candidate is imported in its own process, because the flag is
process-wide and never goes back.
"""
import importlib.metadata as md
import json
import subprocess
import sys

PROBE = r"""
import sys, warnings, json
name = sys.argv[1]
caught = []
warnings.simplefilter("always")
with warnings.catch_warnings(record=True) as w:
    try:
        __import__(name)
    except Exception as exc:
        print(json.dumps({"name": name, "status": "import-error",
                          "detail": f"{type(exc).__name__}: {exc}"}))
        raise SystemExit(0)
    for item in w:
        text = str(item.message)
        if "global interpreter lock" in text:
            caught.append(text)
print(json.dumps({"name": name,
                  "gil": sys._is_gil_enabled(),
                  "warnings": caught}))
"""

names = set()
for dist in md.distributions():
    for top in (dist.read_text("top_level.txt") or "").split():
        if top and not top.startswith("_"):
            names.add(top)

results = []
for name in sorted(names):
    out = subprocess.run([sys.executable, "-c", PROBE, name],
                         capture_output=True, text=True)
    line = out.stdout.strip().splitlines()
    if line:
        results.append(json.loads(line[-1]))

offenders = [r for r in results if r.get("gil")]
print(f"probed {len(results)} top-level packages\n")
if not offenders:
    print("none re-enable the GIL")
for r in offenders:
    print(f"{r['name']}:")
    for w in r["warnings"] or ["(no warning text)"]:
        print(f"    {w}")
