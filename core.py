import heapq
import threading
import time

PADS = [40,41,42,43,48,49,50,51,36,37,38,39,44,45,46,47]
PADS2 = [n+16 for n in PADS]
STEPS = 64

class Model:
    def __init__(self):
        self.patterns = [[[[None]*STEPS for _ in range(128)] for _ in range(9)] for _ in range(8)]
        self.pattern=0; self.playing=0; self.channel=0
        self.selected=36; self.base=36; self.page=0
        self.velocity=100; self.length=100; self.bpm=120
        self.undo_stack=[]; self.redo_stack=[]; self.transaction=None
    @property
    def notes(self): return self.patterns[self.pattern][self.channel]
    def select(self,n):
        self.selected=n
        if not self.base<=n<self.base+16: self.base=min(112,n//16*16)
    def begin(self):
        self.commit(); self.transaction=[]
    def commit(self):
        if self.transaction:
            self.undo_stack.append(self.transaction)
            self.undo_stack=self.undo_stack[-100:]; self.redo_stack.clear()
        self.transaction=None
    def set_cell(self,p,c,n,s,value):
        old=self.patterns[p][c][n][s]
        value=tuple(value) if value is not None else None
        if old==value:return
        change=(p,c,n,s,old,value);self.patterns[p][c][n][s]=value
        if self.transaction is not None:self.transaction.append(change)
        else:
            self.undo_stack.append([change]);self.undo_stack=self.undo_stack[-100:];self.redo_stack.clear()
    def edit(self,n,s,on=None):
        self.select(n)
        if on is None:on=self.notes[n][s] is None
        self.set_cell(self.pattern,self.channel,n,s,(self.velocity,self.length) if on else None)
    def history(self,redo=False):
        self.commit();source=self.redo_stack if redo else self.undo_stack
        if not source:return
        changes=source.pop()
        for p,c,n,s,old,new in (changes if redo else reversed(changes)):
            self.patterns[p][c][n][s]=new if redo else old
        (self.undo_stack if redo else self.redo_stack).append(changes)
    def clear(self,scope):
        self.begin()
        for c in (range(9) if scope=='pattern' else [self.channel]):
            for n in ([self.selected] if scope=='note' else range(128)):
                for s in range(STEPS):self.set_cell(self.pattern,c,n,s,None)
        self.commit()
    def copy_to(self,target,note_only=False):
        if target==self.pattern:return
        self.begin()
        for n in ([self.selected] if note_only else range(128)):
            for s,value in enumerate(self.notes[n]):self.set_cell(target,self.channel,n,s,value)
        self.commit()
    def dump(self):return {'version':2,'patterns':self.patterns,'bpm':self.bpm}
    def load(self,data):
        if isinstance(data,list):
            if len(data)!=128 or any(len(row)!=16 for row in data):raise ValueError('Legacy pattern shape')
            patterns=[[[[None]*64 for _ in range(128)] for _ in range(9)] for _ in range(8)]
            patterns[0][0]=[row+[None]*48 for row in data];bpm=120
        else:
            if data.get('version')!=2:raise ValueError('Unsupported project version')
            patterns=data['patterns'];bpm=data['bpm']
        if not isinstance(bpm,(int,float)) or not 30<=bpm<=300:raise ValueError('Invalid BPM')
        if len(patterns)!=8:raise ValueError('Expected 8 patterns')
        for pat in patterns:
            if len(pat)!=9:raise ValueError('Expected 9 channels')
            for channel in pat:
                if len(channel)!=128:raise ValueError('Expected 128 notes')
                for row in channel:
                    if len(row)!=64:raise ValueError('Expected 64 steps')
                    for cell in row:
                        if cell is not None and (len(cell)!=2 or any(type(x)!=int for x in cell) or not 1<=cell[0]<=127 or not 15<=cell[1]<=300):raise ValueError('Invalid step')
        self.patterns=[[[[tuple(v) if v is not None else None for v in row] for row in ch] for ch in p] for p in patterns]
        self.bpm=bpm;self.undo_stack.clear();self.redo_stack.clear();self.transaction=None

class Pickup:
    """Absolute CC pickup: acquire near/crossing target, then limit each change."""
    def __init__(self):self.states={}
    def reset(self):self.states.clear()
    def value(self,key,raw,target,lo,hi):
        physical=lo+(hi-lo)*raw/127
        previous,latched,last_target=self.states.get(key,(None,False,target))
        if abs(last_target-target)>1:previous=None;latched=False
        if not latched:
            latched=abs(physical-target)<=(hi-lo)*2/127 or (previous is not None and (previous-target)*(physical-target)<=0)
        self.states[key]=(physical,latched,target)
        if not latched:return None
        limit=max(1,(hi-lo)/16)
        result=round(target+max(-limit,min(limit,physical-target)))
        self.states[key]=(physical,True,result)
        return result

class Clock:
    def __init__(self,model,send):
        self.model=model;self.send=send;self.running=False;self.paused=False;self.step=-1;self.tick=0
        self.lock=threading.RLock();self.pending=[];self.active=set();self.closed=False
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def release(self):
        for c,n in self.active:self.send('note_off',channel=c,note=n,velocity=0)
        self.active.clear();self.pending.clear()
    def stop(self):
        with self.lock:
            self.running=False;self.send('stop');self.release();self.step=-1;self.tick=0;self.paused=False
    def toggle(self):
        with self.lock:
            if self.running:self.stop()
            else:
                self.paused=False;self.tick=0;self.next=time.perf_counter();self.running=True;self.send('start')
    def pause_toggle(self):
        with self.lock:
            if self.running:
                self.remaining=max(0,self.next-time.perf_counter());self.running=False;self.paused=True;self.send('stop');self.release()
            elif self.paused:
                self.next=time.perf_counter()+self.remaining;self.paused=False;self.running=True;self.send('continue')
            else:self.toggle()
    def switch_pattern(self,p):
        with self.lock:self.release();self.model.playing=p
    def advance(self,now):
        while self.pending and self.pending[0][0]<=now:
            _,c,n=heapq.heappop(self.pending);self.send('note_off',channel=c,note=n,velocity=0);self.active.discard((c,n))
        if not self.running or now<self.next:return
        self.send('clock')
        if self.tick%6==0:
            self.step=(self.tick//6)%STEPS
            for c,channel in enumerate(self.model.patterns[self.model.playing]):
                for n,row in enumerate(channel):
                    cell=row[self.step]
                    if cell:
                        if (c,n) in self.active:
                            self.send('note_off',channel=c,note=n,velocity=0)
                            self.pending=[x for x in self.pending if x[1:]!=(c,n)];heapq.heapify(self.pending)
                        self.send('note_on',channel=c,note=n,velocity=cell[0]);self.active.add((c,n))
                        heapq.heappush(self.pending,(now+60/self.model.bpm/4*cell[1]/100,c,n))
        self.tick+=1;self.next+=60/self.model.bpm/24
        if now-self.next>.1:self.next=now+60/self.model.bpm/24
    def loop(self):
        while not self.closed:
            with self.lock:self.advance(time.perf_counter())
            time.sleep(.001)
    def close(self):self.stop();self.closed=True;self.thread.join()
