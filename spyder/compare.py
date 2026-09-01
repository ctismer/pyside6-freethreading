"""Compare two columns test by test.

    python compare.py logs/ft-gil0 logs/twin

Counts are not enough: two columns can agree on the number and disagree on
which tests. What matters is the set, and which side ran a test at all -
a file that crashes takes its remaining tests with it.
"""
import glob
import os
import sys
import xml.etree.ElementTree as ET


def sets(path):
    bad, ran = set(), set()
    for p in glob.glob(os.path.join(path, "*.xml")):
        for case in ET.parse(p).getroot().iter("testcase"):
            name = f"{case.get('classname')}::{case.get('name')}"
            ran.add(name)
            if case.find("failure") is not None or case.find("error") is not None:
                bad.add(name)
    return bad, ran


left, right = sys.argv[1], sys.argv[2]
lbad, lran = sets(left)
rbad, rran = sets(right)
print(f"{left:16} {len(lran)} ran, {len(lbad)} bad")
print(f"{right:16} {len(rran)} ran, {len(rbad)} bad")
print()
only_left = (lbad - rbad) & rran
only_right = (rbad - lbad) & lran
print(f"bad in {left} only, and green in {right}: {len(only_left)}")
for n in sorted(only_left):
    print("   ", n)
print(f"bad in {right} only, and green in {left}: {len(only_right)}")
for n in sorted(only_right):
    print("   ", n)
print(f"ran in one column only: {len(lran ^ rran)}")
