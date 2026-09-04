# The A/B harness and the kill-switch matrix

A sanitizer says what a run touched. It does not say whether a lock is
needed. That is what these two runners are for: they take a lock away and
see whether the same binary then breaks.

- `tests/manually/freethreading/run.py` in the PySide tree — the A/B
  harness, one scenario at a time, its own bit cleared.
- [`../ft-apps/killswitch.sh`](../ft-apps/killswitch.sh) — the same
  scenarios across four settings plus a GIL column.

Logs: [`../ft-apps/sanitizer-runs/`](../ft-apps/sanitizer-runs/) —
`0904-killswitch-Deep-Thought-1`, `0904-killswitch-Amrumer-1`.

## What the harness does

Every scenario runs twice against the **same** free-threaded binary: once
with all locks on, once with the one bit its race is about cleared. The
bits are `PYSIDE6_OPTION_FT` from `sbkftoptions.h`:

```
LazyTypeLock = 0x1    serializes lazy type creation
StateLock    = 0x2    the short-lived lock on the binding state
CallGuard    = 0x4    serializes calls reaching one C++ object
```

Each scenario is launched as a fresh subprocess, `REPEATS` times. A
subprocess killed by a signal (SIGSEGV/SIGABRT, i.e. a negative return
code) is a real C++ data race. The proof wanted is

```
unlocked -> crashes    AND    locked -> clean
```

Scenarios come in two kinds, and the distinction is the whole point. A
**proof** scenario has to crash with its lock switched off — that is what
shows it reaches the race at all; passing both ways proves nothing, it
may simply never have collided. A **regression** scenario is only
required to stay clean; it is kept because it once broke.

This is deliberately not part of the automatic test suite: half of the
proof consists of processes dying from SIGSEGV.

## The scenarios

Nine carry a proof mark, five are regression guards.

| scenario | bit it clears | proof | what it is |
|---|---|---|---|
| shared_delete | State | yes | one wrapper deleted while others use it |
| call_vs_delete | State | yes | a call arriving as the object goes |
| child_delete_vs_call | State | yes | destruction taking children with it |
| signal_race | State | yes | connect/emit/disconnect from many threads |
| lookup_vs_last_decref | State | no | fixed by `acquireWrapper()`, not by a lock |
| destroy_race | State | no | every thread owns its objects; nothing contended |
| lazy_converter | Lazy+Guard | yes | the one-time incarnation of a type, raced |
| lazy_types | Lazy | yes | Qt's QML loader thread incarnates types |
| shared_setter | Guard | yes | every thread inside one C++ object at once |
| queued_signal | State | no | a queued connection across threads |
| move_to_thread | State | **yes** | an object handed over while still in use |
| container_convert | Lazy | **yes** | converting a container incarnates its element type |
| dynamic_property | State | no | = finding 5, an ordinary PySide bug |
| virtual_override | State | no | drives the caches of findings 2 and 3 |

`lazy_converter` clears the call guard along with the lazy bit: the guard
serializes calls on one object as a side effect, which hides this race
and made the scenario inconclusive once CallGuard entered ALL. What is
proven is still the lazy lock — the guard is only kept out of the way.

`lazy_types` is the QML test and needs a display, so the sanitizer runs
use the other thirteen.

## What the kill switch measured

Five rounds per column, both machines, 04.09.2026:

```
                    Deep-Thought              Amrumer
scenario         on    OFF   GIL on      on    OFF   GIL on
queued_signal    0/5   0/5    0/5       0/5   1/5    0/5
move_to_thread   0/5   5/5    0/5       0/5   5/5    0/5
container_conv   0/5   4/5    0/5       0/5   5/5    0/5
dynamic_prop     5/5   5/5    5/5       5/5   5/5    5/5
virtual_overr    0/5   0/5    0/5       0/5   0/5    0/5
```

`move_to_thread` and `container_convert` break without the locks and hold
with them. That is the first time a scenario taken from an **application
pattern** — not from a code path we set out to prove — carries a lock.

Which lock, switched off one at a time:

```
scenario            all on   no lazy   no state   no guard   all off
move_to_thread        0/5      0/5       5/5        0/5       5/5
container_convert     0/5      5/5       0/5        0/5       5/5
```

`move_to_thread` hangs on the state lock, `container_convert` on the
**lazy type lock** — where `Lock.STATE` stood as an assumption in the
table. Both are marked as proofs in `run.py` now, with this matrix as the
comment beside them.

`queued_signal` and `virtual_override` stay unmarked: they run through
without locks as well. The single failure of `queued_signal` on amrumer
is too little to build on — a proof mark needs a picture like the two
above, not an outlier. `virtual_override` earns its keep anyway: it is
what produces the ThreadSanitizer reports for findings 2 and 3.

`dynamic_property` crashes in every column including the GIL one. That is
[finding 5](asan.md#finding-5--a-qobject-stored-as-a-dynamic-property),
kept so the crash stays visible until it is fixed.

## Traps, each one walked into once

**The tree has to match the tool.** `killswitch.sh` once ran on an ASan
tree and delivered "5/5 everywhere in 2 seconds" — that was
"interceptors not installed", not a result. Both runners now check with
`nm`.

**Three tools guess the build.** After an FT build, FT suite, GIL build,
GIL suite, the most recent `build_history` entry is the GIL tree. The A/B
run went that way once — the 3.15t interpreter against the 3.12 package —
reported 15err/15 in every scenario and looked like a broken kill switch.
`run.py` has `BUILD_DIR`, `gil-view.py` has `--build`, `check-accept.py`
writes the entry itself.

**A run without the sample binding reads like a result.** Without
`--build-tests` every scenario fails to import, and a full run of failed
starts looks like a full run. `run.py` checks for the sample module and
refuses.

**At a 7–13 % hit rate, five or fifteen rounds are too few.**
`call_vs_delete` was 0/15 (INCONCLUSIVE); at 45 repetitions it was
3 CRASH/45 and PROVEN. `check-accept.py` repeats an inconclusive proof
scenario automatically at three times the count.

**The 20-minute limit that exits 0.** `testing/command.py` had
`TIMEOUT = 20 * 60` per project. When it expires, `runner.py` kills ctest,
prints "aborted, partial result" — and testrunner exits **0**. Under a
sanitizer everything is about ten times slower, so the second half of the
suite tore off: at test 201 the first time, at 229 of 543 on 04.09. The
summary then said "rc 0, reports 0, no failures". A half run without
findings looks exactly like a clean one. `TIMEOUT` now reads
`PYSIDE_TEST_TIMEOUT`, `suite-sanitize.sh` sets two hours and prints
INCOMPLETE with the last test number. The torn-off run is kept as
`0904-suite-tsan-Amrumer-1-INCOMPLETE` to look at.

## What an application suite cannot do

The napari suite proves none of these locks: all four kill-switch
settings deliver the same 13 failures, test for test. "napari runs
clean" is not evidence of thread safety — see
[../RESULTS.md](../RESULTS.md).
