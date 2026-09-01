"""Sum up the junit files of one column and list what failed.

    python aggregate.py logs/ft-gil0
"""
import glob
import os
import sys
import xml.etree.ElementTree as ET

out = sys.argv[1]
tests = failures = errors = skipped = 0
names = []
for path in sorted(glob.glob(os.path.join(out, "*.xml"))):
    root = ET.parse(path).getroot()
    for suite in root.iter("testsuite"):
        tests += int(suite.get("tests", 0))
        failures += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            if case.find(kind) is not None:
                names.append(f"{kind[0].upper()} {case.get('classname')}"
                             f"::{case.get('name')}")
                break
print(f"{out}: {tests} tests, {failures} failed, {errors} errors, "
      f"{skipped} skipped")
for name in sorted(set(names)):
    print("   ", name)
