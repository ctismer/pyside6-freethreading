# Acceptance run, 2026-09-04, Deep-Thought

`./check-accept.py`, both arms, 18 minutes end to end. Branch
`phase1-lease-owner` at `bd0b0abf8`, Qt 6.12.0, the first run after
check-accept.py was moved to `testrunner --build`.

```
ok    free-threaded 3.15t  build       rc 0, no errors
ok    free-threaded 3.15t  suites      pyside6 541/543  shiboken6 158/158  generator 37/37
FAIL  free-threaded 3.15t  A/B         FAILED, 15 repeats  -> dynamic_property
ok    GIL 3.12             build       rc 0, no errors
ok    GIL 3.12             suites      pyside6 541/543  shiboken6 158/158  generator 37/37
```

The two missing tests are the known foreign ones: `QtUiTools_loadUiType`
(needs uic, we build `--no-qt-tools`) and `pyside6-deploy`.

## The A/B proof

Every proof scenario crashes without its lock and is clean with it — all
nine of them, for the first time in one run.

```
scenario              unlocked    locked      kind
--------------------------------------------------
shared_delete         15CRASH/15  ok/15       proof
call_vs_delete        15CRASH/15  ok/15       proof
child_delete_vs_call  15CRASH/15  ok/15       proof
signal_race           15CRASH/15  ok/15       proof
lookup_vs_last_decref ok/15       ok/15       regression
destroy_race          ok/15       ok/15       regression
lazy_converter        12CRASH/15  ok/15       proof
lazy_types            5CRASH/15   ok/15       proof
shared_setter         15CRASH/15  ok/15       proof
queued_signal         2CRASH/15   ok/15       regression
move_to_thread        15CRASH/15  ok/15       proof
container_convert     15CRASH/15  ok/15       proof
dynamic_property      15CRASH/15  15CRASH/15  regression
virtual_override      ok/15       ok/15       regression
```

`call_vs_delete` is worth a note: it came back 0/15 INCONCLUSIVE once and
needed 45 repeats to be PROVEN. At 15 it now hits every time — the same
scenario, a later build.

## Why the run is red

`dynamic_property` crashes in **both** columns, 15 of 15. That is
finding 5, the release bug: storing a QObject as a dynamic property and
reading it back segfaults with the GIL as well and on PySide6 6.11.2. It
is kept in the harness so the crash stays visible, so every acceptance run
ends red until it is fixed.

## One thing to follow up

`queued_signal` crashed 2 of 15 without the state lock, having been 0/5 on
both machines before. 13 % is exactly the hit rate at which five rounds
say nothing — `call_vs_delete` sat there too. Worth re-running at 45
repeats before deciding whether it earns a proof mark.

## What is in here

```
logs/          what check-accept.py wrote: the two builds, the two suite
               runs, the A/B table
ctest-py3.15/  the build_history entry of the free-threaded tree, i.e.
               the per-project ctest logs testrunner wrote
ctest-py3.12/  the same for the GIL tree
```
