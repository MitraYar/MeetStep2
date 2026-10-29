# CPU benchmark

Measured in the Linux cloud environment with Python 3.12, Tk and a 1280×800 dummy
X display. These figures compare process CPU against one logical core, not total
machine CPU. No physical MIDI device was attached. Windows/hardware results may differ.

Three-second samples after a 250 ms warmup; same 120 BPM pattern on nine channels.
Baseline: commit `9b8c54c`, before Select Mode, recording and CPU changes.

| State | Before, one core | After, one core | Redraws before / after | Scheduler wakes before / after |
| --- | ---: | ---: | ---: | ---: |
| Idle | 18.53% | 1.08% | 123 / 0 | 2745 / 60 |
| Playing | 20.82% | 5.20% | 121 / 25 | 2612 / 145 |

The grid redraws only when visible state changes. RGB palettes are cached until
their inputs change. Drone sets are recomputed on changes to drones, mutes,
transport or the playing pattern. The MIDI worker waits for the next clock tick,
note-off, swung onset or envelope update; it no longer polls every millisecond.
Pitch envelopes use 4 ms updates while moving. MIDI Clock remains at 24 PPQN.

Run from a source checkout with a graphical session and installed requirements:

```text
python tools/benchmark_cpu.py . idle
python tools/benchmark_cpu.py . play
```

Pass another source checkout as the first argument for comparison. The benchmark
uses temporary settings and no configured MIDI ports. It prints CPU time, elapsed
time, redraw count and scheduler wake count as JSON. The test suite also checks
that unchanged GUI state does not trigger another redraw.
