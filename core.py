import time, threading, heapq
PADS = [40,41,42,43,48,49,50,51,36,37,38,39,44,45,46,47]
class Model:
    def __init__(self):
        self.notes = [[None]*16 for _ in range(128)]
        self.selected=36; self.base=36; self.velocity=100; self.length=100; self.bpm=120
    def select(self,n):
        self.selected=n
        if not self.base<=n<self.base+16: self.base=min(112,n//16*16)
    def edit(self,n,s,on=None):
        self.select(n)
        if on is None: on=self.notes[n][s] is None
        self.notes[n][s]=(self.velocity,self.length) if on else None
class Clock:
    def __init__(self,model,send):
        self.model=model; self.send=send; self.running=False; self.step=-1; self.tick=0; self.paused=False
        self.lock=threading.RLock(); self.pending=[]; self.active=set(); self.closed=False
        self.thread=threading.Thread(target=self.loop,daemon=True); self.thread.start()
    def stop(self):
        with self.lock:
            self.running=False; self.send('stop')
            for n in self.active: self.send('note_off',note=n,velocity=0)
            self.active.clear(); self.pending.clear(); self.step=-1; self.tick=0; self.paused=False
    def toggle(self):
        with self.lock:
            if self.running: self.stop()
            else:
                self.paused=False; self.tick=0; self.next=time.perf_counter(); self.running=True; self.send('start')
    def pause_toggle(self):
        with self.lock:
            if self.running:
                self.remaining=max(0,self.next-time.perf_counter())
                self.running=False;self.paused=True;self.send('stop')
                for n in self.active:self.send('note_off',note=n,velocity=0)
                self.active.clear();self.pending.clear()
            elif self.paused:
                self.next=time.perf_counter()+self.remaining
                self.paused=False;self.running=True;self.send('continue')
            else:self.toggle()
    def loop(self):
        while not self.closed:
            with self.lock:
                now=time.perf_counter()
                while self.pending and self.pending[0][0]<=now:
                    _,n=heapq.heappop(self.pending); self.send('note_off',note=n,velocity=0);self.active.discard(n)
                if self.running and now>=self.next:
                    self.send('clock')
                    if self.tick%6==0:
                        self.step=(self.tick//6)%16
                        for n,row in enumerate(self.model.notes):
                            cell=row[self.step]
                            if cell:
                                if n in self.active:
                                    self.send('note_off',note=n,velocity=0)
                                    self.pending=[x for x in self.pending if x[1]!=n];heapq.heapify(self.pending)
                                self.send('note_on',note=n,velocity=cell[0]);self.active.add(n)
                                heapq.heappush(self.pending,(now+60/self.model.bpm/4*cell[1]/100,n))
                    self.tick+=1;self.next+=60/self.model.bpm/24
                    if now-self.next>.1:self.next=now+60/self.model.bpm/24
            time.sleep(.001)
    def close(self):
        self.stop();self.closed=True;self.thread.join()
