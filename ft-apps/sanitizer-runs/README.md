# Sanitizer runs

One directory per run, never appended to, never reused:

    <MMDD>-<tool>-<host>-<n>/

`tool` is `tsan`, `asan` or `killswitch`; `host` is the machine.
Every directory holds a `summary.txt` with the exact build tree,
interpreter, runtime library and options that produced it, plus one log
per scenario. The summary is the record - the numbers in
`../../tsan-befunde.md` are read off these files.

## How they were made

    ft-apps/build-python.sh tsan          # instrumented CPython, once per machine
    ft-apps/build-sanitizer.sh tsan       # -> build-tsan/
    ft-apps/build-sanitizer.sh asan       # -> build-asan/
    ft-apps/build-sanitizer.sh none       # -> build/, the control

    ft-apps/sanitize.sh tsan build-tsan/<tree>
    ft-apps/sanitize.sh asan build-asan/<tree>
    ft-apps/killswitch.sh build/<tree> 5

`ft-apps/ft-env.sh` names the interpreters, Qt and branch, so the same
command means the same thing on either machine. `ft-apps/machine-state.sh`
prints what a machine has; diff it against the other one.

## What the runs are worth

A summary without the right interpreter is worth nothing. TSan needs a
`libpython` built `--with-thread-sanitizer` - against an ordinary one it
reports CPython, not us, and the log looks exactly like a real finding.
`sanitize.sh` refuses to run if the interpreter was not built that way,
and both runners check what the build tree is instrumented with before
they start. Both checks exist because both mistakes were made here first.

## The runs kept

    0903-tsan-scenarios             first TSan pass, eight scenarios
    0904-asan-scenarios             first ASan pass, same eight
    0904-tsan-Deep-Thought-1        thirteen scenarios, instrumented CPython
    0904-tsan-Amrumer-1             the same, second machine
    0904-asan-Deep-Thought-1        thirteen scenarios
    0904-asan-Amrumer-1             the same, second machine
    0904-killswitch-Deep-Thought-1  locks on / off / GIL on, five rounds each
    0904-killswitch-Amrumer-1       the same, second machine
    0904-suite-asan-Deep-Thought-1  the whole test suite under ASan
    0904-suite-asan-Amrumer-1       the same, second machine, same result
    0904-suite-tsan-Deep-Thought-1  the same under TSan
    0904-suite-tsan-Amrumer-1-INCOMPLETE
                                    kept as the example: killed by
                                    testrunner's own 20-minute limit at
                                    test 229 of 543, and the summary said
                                    "rc 0, reports 0" all the same

## The 20-minute trap

`testing/command.py` kills ctest after TIMEOUT seconds per project,
prints "aborted, partial result" and exits 0. Under a sanitizer
everything runs about ten times slower, so the second half of the suite
silently does not run - a partial result that reads exactly like a clean
one. That is what the "suite abort at test 201" was.

TIMEOUT now reads `PYSIDE_TEST_TIMEOUT`; `suite-sanitize.sh` sets it to
two hours and prints INCOMPLETE with the last test number when a run is
cut short anyway.
