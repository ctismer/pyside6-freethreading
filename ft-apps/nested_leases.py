"""Find call guards that open while another is still in scope.

Two leases at once are fine - a lease is a counter. What must not nest is the
per-object call guard: it is a PyCriticalSection, and CPython resumes only the
top-most one after a detach, so an inner section silently drops the outer
one's lock (cpython/critical_section.h). Only the receiver takes a guard;
arguments are generated with Guard::Omit. "nested guards" has to read 0.

Generated wrappers carry both preprocessor arms, and the two arms open braces
independently - counting the text of both makes the depth drift and reports
neighbouring functions as nested. So the arms are resolved first, for the
free-threaded build, and only then does brace depth decide.

LIMIT: this sees lexical nesting only. A guard taken inside a function this
one calls does not show up here - which is exactly how the copy converter kept
a Guard::Take for a while, in a converter function of its own. Whether a
callee opens one has to be read, not counted.

Usage:  nested_leases.py <generated tree or single file>
"""
import pathlib
import re
import sys

LEASE = "Shiboken::Object::CallLease "
IF = re.compile(r"#\s*if(n?)def\s+(\w+)|#\s*if\s+(.*)")
ELSE = re.compile(r"#\s*else\b")
ELIF = re.compile(r"#\s*elif\b")
ENDIF = re.compile(r"#\s*endif\b")


def free_threaded_arm(lines):
    """The lines a free-threaded build compiles. Conditions other than
    Py_GIL_DISABLED are unknown here, so both of their arms are kept - they
    are balanced in themselves and do not disturb the depth."""
    # stack entries: None for an unknown condition, else True/False for
    # "this arm is compiled"
    stack = []
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if ENDIF.match(stripped):
            if stack:
                stack.pop()
            continue
        if ELSE.match(stripped):
            if stack and stack[-1] is not None:
                stack[-1] = not stack[-1]
            continue
        if ELIF.match(stripped):
            if stack and stack[-1] is not None:
                stack[-1] = False       # the #ifdef arm already decided it
            continue
        m = IF.match(stripped)
        if m:
            if m.group(2) == "Py_GIL_DISABLED":
                stack.append(m.group(1) != "n")
            else:
                stack.append(None)
            continue
        if all(s is not False for s in stack):
            yield lineno, line


root = pathlib.Path(sys.argv[1])
paths = sorted(root.rglob("*_wrapper.cpp")) if root.is_dir() else [root]

files = leases = guards = nested = 0
examples = []

for path in paths:
    depth = 0
    open_guards = []          # (depth, line number)
    for lineno, line in free_threaded_arm(
            path.read_text(errors="ignore").splitlines()):
        stripped = line.strip()
        if stripped.startswith(LEASE):
            leases += 1
            if "Guard::Omit" not in line:
                guards += 1
                if open_guards:
                    nested += 1
                    if len(examples) < 8:
                        examples.append((path.name, open_guards[-1][1], lineno))
                open_guards.append((depth, lineno))
        depth += line.count("{") - line.count("}")
        open_guards = [(d, ln) for d, ln in open_guards if d <= depth]
    files += 1

print(f"files:          {files}")
print(f"leases:         {leases}")
print(f"guards:         {guards}")
print(f"nested guards:  {nested}   (has to be 0)")
for name, outer, inner in examples:
    print(f"   {name}: outer {outer}, inner {inner}")
