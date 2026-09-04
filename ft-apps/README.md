# Applications used to validate free-threaded PySide6

Two real applications, run against our own free-threaded PySide6 wheels, to
answer one question: does anything break that does not break with a GIL?

Everything an app needs lives in its own directory here - the environment
recipe, the runners, and every log a claim in `FINDINGS.md` rests on. The
checkouts themselves stay where they are (`~/src/napari`, `~/src/spyder`,
`~/src/spyder-kernels`); the setup scripts take their location from
`$NAPARI` / `$SPYDER` / `$KERNELS` and default to those paths.

    ft-apps/
        napari/
            setup-venv.sh     build the environment
            run-app.py        open a viewer, report the GIL state
            run-suite.sh      the Qt suite, once per GIL setting
            gilscan.py        which installed package turns the GIL back on
            FINDINGS.md       what came out
            logs/             every run behind those findings
        spyder/
            setup-venvs.sh    two environments: free-threaded, and the control
            run-app.py        start Spyder, report the GIL state
            run-suite.sh      the suite, one process per test directory
            aggregate.py      sum up one column's junit files
            gilscan.py
            FINDINGS.md
            logs/

The venvs are built, not committed, and are excluded from git along with the
rest of this tree.

## The method, and why it is the way it is

**Two columns, never one.** Every suite runs twice against the same wheels,
`PYTHON_GIL=1` and `PYTHON_GIL=0`. A test that fails in both is napari's or
Spyder's or the machine's. Only a test that fails without the GIL and passes
with it belongs to us. A single red column proves nothing.

**A third column when a crash turns up.** Spyder crashes; the question is
then whether it crashes because of us. `venv-gil` answers it: CPython 3.12,
PySide6 from PyPI, the same Spyder checkout. Our chain also carries kill
switches (`PYSIDE6_OPTION_FT=off`), which take the locks out of the same
binary. A crash that survives both is not ours.

**`gilscan.py` before anything else.** On a free-threaded interpreter, one
extension module without a free-threading declaration switches the GIL back
on process-wide, and it never goes off again. Then the whole run measures
nothing. The scan imports every top-level package in its own process and
names the offenders - a list Neil Schemenauer wants for the ecosystem work.

**`-s` on every pytest run.** Without it pytest swallows the stderr of tests
that pass, which is exactly where the Qt warnings and the timeouts appear.

## Two machines

GUI suites take the screen hostage: pytest-qt opens windows, types into
them and needs the focus, so a run makes the machine unusable for anything
else, and two runs at once make each other flaky - sixteen keyboard tests
failed once for no other reason than windows left standing by an earlier
test file.

So the work is split. Builds happen on the machine that has Qt 6.12; test
runs happen on `amrumer.local`, an M3 with the same account and the same
paths.

It is normally switched off, to spare the battery. Ask before planning a
run on it - that it answers a ping means it happens to be on, not that it
is free.

    ~/.pyenv/versions/3.14.3t     rsync'ed over rather than rebuilt, so the
                                  interpreter is bit-identical
    ~/src/QtC/pyside-setup        without build/ and build_history/
    ~/src/spyder                  the same commits as here
    ~/src/spyder-kernels
    ~/src/napari

The wheels travel with the repo in `dist/`, which is what standalone wheels
are for: `amrumer` has no Qt 6.12 and does not need one.

A Qt application reaches the window server over SSH there, because the same
account is logged in on the console. Check it before trusting a run:

    ssh amrumer.local 'cd src/QtC/pyside-setup/ft-apps/spyder &&
        ./venv-ft/bin/python -c "
    from PySide6.QtWidgets import QApplication, QLabel
    app = QApplication([]); QLabel(\"probe\").show()
    print(\"window server ok, screens:\", len(app.screens()))"'
