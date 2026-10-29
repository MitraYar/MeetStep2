"""Source benchmark: python tools/benchmark_cpu.py [checkout] [idle|play]."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

checkout=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
mode=sys.argv[2] if len(sys.argv)>2 else 'idle'
sys.path.insert(0,str(checkout))
import app

with tempfile.TemporaryDirectory() as temp,patch.object(app,'CONFIG',Path(temp)/'settings.json'):
    a=app.App(run=False)
    if mode=='play':
        for c in range(9):
            for s in range(0,64,4):a.model.set_cell(0,c,36+c,s,(90,100))
        a.clock.toggle()
    count={'redraws':0,'scheduler_wakes':0};draw=a.draw;advance=a.clock.advance
    def tracked_draw():count['redraws']+=1;draw()
    def tracked_advance(now):count['scheduler_wakes']+=1;advance(now)
    def start():
        a.draw=tracked_draw;a.clock.advance=tracked_advance
        start_wall=time.perf_counter();start_cpu=time.process_time()
        def finish():
            wall=time.perf_counter()-start_wall;cpu=time.process_time()-start_cpu
            print(json.dumps({'mode':mode,'seconds':round(wall,3),'cpu_ms':round(cpu*1000,1),'one_core_percent':round(cpu/wall*100,2),**count}))
            a.close()
        a.root.after(3000,finish)
    a.root.after(250,start);a.root.mainloop()
