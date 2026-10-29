"""Compare 16/64-cell scaling in a checkout, with and without whole-step copy scope."""
import json
import pathlib
import statistics
import sys
import time

sys.path.insert(0,str(pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()))
from core import Model
from editor import Editor

for count in (16,64):
    for scope in ('note','all_channels'):
        m=Model();e=Editor(m)
        for c in range(9):
            for n in (36,40):
                for s in range(64):m.set_cell(0,c,n,s,(60,100))
        e.selection={(36,s) for s in range(count)};e.scope=scope;m.undo_stack.clear();durations=[]
        for i in range(60):
            start=time.perf_counter();e.scale('velocity',.5+(i%20)/20);durations.append((time.perf_counter()-start)*1000)
        print(json.dumps({'cells':count,'copy_scope':scope,'median_ms':round(statistics.median(durations),3),
                          'p95_ms':round(sorted(durations)[56],3),'changed_per_event':len(m.undo_stack[-1]['changes'])}))
