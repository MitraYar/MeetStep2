import heapq
import threading
import time
import copy
from collections import deque
from pitch import PitchEngine

PADS = [40,41,42,43,48,49,50,51,36,37,38,39,44,45,46,47]
PADS2 = [n+16 for n in PADS]
STEPS = 64

class Model:
    def __init__(self):
        self.patterns = [[[[None]*STEPS for _ in range(128)] for _ in range(9)] for _ in range(8)]
        self.pattern=0; self.playing=0; self.channel=0
        self.lengths=[64]*8;self.mono=[False]*9;self.swing=0
        self.revision=0;self.drone_revision=0;self.on_change=lambda:None
        self.selected=36;self.bases=[36]*9;self.page=0
        self.muted=[False]*9
        self.drones=[[[False]*128 for _ in range(9)] for _ in range(8)]
        self.note_modes=[[['gate']*128 for _ in range(9)] for _ in range(8)]
        self.pitch_presets=[{'micro':0,'bend':0} for _ in range(9)]
        self.capture_context=lambda: {'pattern':self.pattern,'channel':self.channel,'selected':self.selected,'base':self.base,'page':self.page}
        self.restore_context=self._restore_context
        self.transaction_before=None
        self.velocity=100; self.length=100; self.bpm=120
        self.undo_stack=[]; self.redo_stack=[]; self.transaction=None
    @property
    def notes(self): return self.patterns[self.pattern][self.channel]
    @property
    def base(self):return self.bases[self.channel]
    @base.setter
    def base(self,value):self.bases[self.channel]=max(0,min(112,value))
    def _restore_context(self,context):
        for name in ('pattern','channel','selected','base','page'):setattr(self,name,context[name])
    def select(self,n):
        self.selected=n
        if not self.base<=n<self.base+16:self.base=36+((n-36)//16)*16
    def begin(self):
        self.commit(); self.transaction=[];self.transaction_before=copy.deepcopy(self.capture_context())
    def commit(self):
        if self.transaction:
            self.undo_stack.append({'changes':self.transaction,'before':self.transaction_before,'after':copy.deepcopy(self.capture_context())})
            self.undo_stack=self.undo_stack[-100:]; self.redo_stack.clear()
        self.transaction=None
    def _record(self,kind,index,old,new):
        change=(kind,index,copy.deepcopy(old),copy.deepcopy(new))
        if self.transaction is not None:self.transaction.append(change)
        else:
            context=copy.deepcopy(self.capture_context())
            self.undo_stack.append({'changes':[change],'before':context,'after':context})
            self.undo_stack=self.undo_stack[-100:];self.redo_stack.clear()
    def set_cell(self,p,c,n,s,value):
        old=self.patterns[p][c][n][s]
        value=tuple(value) if value is not None else None
        if old==value:return
        self._record('patterns',(p,c,n,s),old,value);self.patterns[p][c][n][s]=value
        self.touch()
    def touch(self,drones=False):
        self.revision+=1
        if drones:self.drone_revision+=1
        self.on_change()
    def set_meta(self,kind,index,value):
        target=getattr(self,kind)
        for i in index[:-1]:target=target[i]
        old=target[index[-1]]
        if old!=value:self._record(kind,index,old,value);target[index[-1]]=value;self.touch(kind in ('drones','muted'))
    def step_note(self,s,c=None,p=None):
        c=self.channel if c is None else c;p=self.pattern if p is None else p
        return next((n for n,row in enumerate(self.patterns[p][c]) if row[s]),self.selected)
    def write_cell(self,p,c,n,s,value):
        if value is not None and self.mono[c]:
            for other,row in enumerate(self.patterns[p][c]):
                if other!=n and row[s]:self.set_cell(p,c,other,s,None)
        self.set_cell(p,c,n,s,value)
    def edit(self,n,s,on=None,articulation=None):
        self.select(n)
        if on is None:on=self.notes[n][s] is None
        if on and self.notes[n][s] is not None:
            if articulation is not None:self.set_articulation(n,s,articulation)
            return
        value=(self.velocity,self.length)
        preset=self.pitch_presets[self.channel]
        meta=dict(preset) if any(preset.values()) else {}
        if articulation and articulation!='gate':meta['mode']=articulation
        if meta:value+=(meta,)
        self.write_cell(self.pattern,self.channel,n,s,value if on else None)
        if on:self.pitch_presets[self.channel]={'micro':0,'bend':0}
    def set_articulation(self,n,s,mode):
        cell=self.notes[n][s]
        if not cell:return
        meta=dict(cell[2]) if len(cell)>2 else {};meta['mode']=mode
        self.set_cell(self.pattern,self.channel,n,s,cell[:2]+(meta,))
    def toggle_mono(self):
        c=self.channel;enabled=not self.mono[c];self.begin();self.set_meta('mono',(c,),enabled)
        if enabled:
            for p in range(8):
                for s in range(64):
                    notes=[n for n,row in enumerate(self.patterns[p][c]) if row[s]]
                    keep=self.selected if self.selected in notes else (min(notes) if notes else None)
                    for n in notes:
                        if n!=keep:self.set_cell(p,c,n,s,None)
        self.commit()
    def history(self,redo=False):
        self.commit();source=self.redo_stack if redo else self.undo_stack
        if not source:return
        entry=source.pop();changes=entry['changes']
        for kind,index,old,new in (changes if redo else reversed(changes)):
            target=getattr(self,kind)
            for i in index[:-1]:target=target[i]
            target[index[-1]]=copy.deepcopy(new if redo else old)
        self.restore_context(copy.deepcopy(entry['after' if redo else 'before']))
        self.touch(True)
        (self.undo_stack if redo else self.redo_stack).append(entry)
    def clear(self,scope):
        self.begin()
        for c in (range(9) if scope=='pattern' else [self.channel]):
            for n in ([self.selected] if scope=='note' else range(128)):
                for s in range(STEPS):self.set_cell(self.pattern,c,n,s,None)
                self.set_meta('drones',(self.pattern,c,n),False)
                self.set_meta('note_modes',(self.pattern,c,n),'gate')
        self.commit()
    def copy_to(self,target,note_only=False,whole=False):
        if target==self.pattern:return
        self.begin()
        for c in (range(9) if whole else [self.channel]):
            for n in ([self.selected] if note_only else range(128)):
                for s,value in enumerate(self.patterns[self.pattern][c][n]):self.set_cell(target,c,n,s,value)
                self.set_meta('drones',(target,c,n),self.drones[self.pattern][c][n])
        if whole:self.set_meta('lengths',(target,),self.lengths[self.pattern])
        self.commit()
    def dump(self):return {'version':5,'patterns':self.patterns,'bpm':self.bpm,'lengths':self.lengths,'drones':self.drones,'muted':self.muted,'bases':self.bases,'mono':self.mono,'swing':self.swing}
    def load(self,data):
        if isinstance(data,list):
            if len(data)!=128 or any(len(row)!=16 for row in data):raise ValueError('Legacy pattern shape')
            patterns=[[[[None]*64 for _ in range(128)] for _ in range(9)] for _ in range(8)]
            patterns[0][0]=[row+[None]*48 for row in data];bpm=120;lengths=[16]+[64]*7
        else:
            if data.get('version') not in (2,3,4,5):raise ValueError('Unsupported project version')
            patterns=data['patterns'];bpm=data['bpm'];lengths=data.get('lengths',[64]*8)
        if len(lengths)!=8 or any(type(v)!=int or not 1<=v<=64 for v in lengths):raise ValueError('Pattern lengths: 1–64')
        if not isinstance(bpm,(int,float)) or not 30<=bpm<=300:raise ValueError('Invalid BPM')
        if len(patterns)!=8:raise ValueError('Expected 8 patterns')
        for pat in patterns:
            if len(pat)!=9:raise ValueError('Expected 9 channels')
            for channel in pat:
                if len(channel)!=128:raise ValueError('Expected 128 notes')
                for row in channel:
                    if len(row)!=64:raise ValueError('Expected 64 steps')
                    for cell in row:
                        if cell is not None:
                            if len(cell) not in (2,3) or any(type(x)!=int for x in cell[:2]) or not 1<=cell[0]<=127 or not 15<=cell[1]<=300:raise ValueError('Invalid step')
                            if len(cell)==3:
                                from pitch import validate_preset
                                validate_preset(cell[2])
        extra=data if isinstance(data,dict) else {}
        drones=extra.get('drones',[[[False]*128 for _ in range(9)] for _ in range(8)])
        modes=extra.get('note_modes',[[['gate']*128 for _ in range(9)] for _ in range(8)])
        for values,allowed in ((drones,(True,False)),(modes,('gate','legato','nonlegato'))):
            if len(values)!=8 or any(len(p)!=9 or any(len(c)!=128 or any(v not in allowed for v in c) for c in p) for p in values):raise ValueError('Invalid note mode data')
        muted=extra.get('muted',[False]*9);bases=extra.get('bases',[36]*9)
        mono=extra.get('mono',[False]*9);swing=extra.get('swing',0)
        if len(mono)!=9 or any(type(x)!=bool for x in mono) or not isinstance(swing,(int,float)) or not 0<=swing<=100:raise ValueError('Invalid mono / swing')
        if len(muted)!=9 or any(type(x)!=bool for x in muted):raise ValueError('Invalid mutes')
        if len(bases)!=9 or any(type(x)!=int or not 0<=x<=112 for x in bases):raise ValueError('Invalid note ranges')
        self.patterns=[[[[tuple(v) if v is not None else None for v in row] for row in ch] for ch in p] for p in patterns]
        self.bpm=bpm;self.lengths=list(lengths);self.undo_stack.clear();self.redo_stack.clear();self.transaction=None
        self.drones=copy.deepcopy(drones);self.note_modes=copy.deepcopy(modes);self.muted=list(muted);self.bases=list(bases)
        self.mono=list(mono);self.swing=swing
        if extra.get('version',0)<5:
            for p,pattern in enumerate(self.patterns):
                for c,channel in enumerate(pattern):
                    for n,row in enumerate(channel):
                        if modes[p][c][n]=='gate':continue
                        for s,cell in enumerate(row):
                            if cell:
                                meta=dict(cell[2]) if len(cell)>2 else {};meta['mode']=modes[p][c][n];row[s]=cell[:2]+(meta,)
        self.pitch_presets=[{'micro':0,'bend':0} for _ in range(9)]
        self.touch(True)

class ScaleTakeover:
    """Map remaining physical travel proportionally to the remaining value range."""
    def __init__(self):self.states={}
    def reset(self):self.states.clear()
    def value(self,key,raw,target,lo,hi):
        old=self.states.get(key);self.states[key]=(raw,target)
        if old is None or abs(old[1]-target)>1 or raw==old[0]:return None
        delta=raw-old[0]
        value=target+(hi-target)*delta/max(1,127-old[0]) if delta>0 else target+(target-lo)*delta/max(1,old[0])
        value=round(max(lo,min(hi,value)));self.states[key]=(raw,value);return value

class Pickup:
    """Pickup with a deliberate, sustained turn overriding the stored position."""
    FAST_CC_PER_SECOND=24
    OVERRIDE_SECONDS=.3
    MAX_GAP_SECONDS=.12
    def __init__(self,now=time.monotonic):self.states={};self.now=now
    def reset(self):self.states.clear()
    def value(self,key,raw,target,lo,hi):
        now=self.now()
        physical=lo+(hi-lo)*raw/127
        state=self.states.get(key)
        if state is None or abs(state['target']-target)>1:
            state={'raw':None,'time':now,'target':target,'latched':False,'relative':False,'direction':0,'since':None}
        previous_raw=state['raw']
        previous=None if previous_raw is None else lo+(hi-lo)*previous_raw/127
        delta=0 if previous_raw is None else raw-previous_raw
        # Repeated identical CCs must not accumulate an override or move the value.
        if previous_raw is not None and delta==0:return None
        elapsed=now-state['time'];direction=1 if delta>0 else -1
        fast=delta!=0 and 0<elapsed<=self.MAX_GAP_SECONDS and abs(delta)/elapsed>=self.FAST_CC_PER_SECOND
        away=delta*(physical-target)>0
        if fast and away:
            if state['direction']!=direction or state['since'] is None:state['since']=state['time']
            state['direction']=direction
            if now-state['since']>=self.OVERRIDE_SECONDS:state['relative']=True
        else:state['since']=None;state['direction']=0
        if not state['latched']:
            state['latched']=abs(physical-target)<=(hi-lo)*2/127 or (previous is not None and (previous-target)*(physical-target)<=0)
        state.update(raw=raw,time=now,target=target);self.states[key]=state
        if state['relative']:
            # Once forced, follow turn direction from the sequencer's current value.
            # Scale the available physical travel towards each end of the range.
            if delta>0:desired=target+(hi-target)*delta/max(1,127-previous_raw)
            else:desired=target+(target-lo)*delta/max(1,previous_raw)
        elif state['latched']:desired=physical
        else:return None
        limit=max(1,(hi-lo)/16)
        result=round(max(lo,min(hi,target+max(-limit,min(limit,desired-target)))))
        state['target']=result
        return result

class Clock:
    def __init__(self,model,send):
        self.model=model;self.send=send;self.running=False;self.paused=False;self.step=-1;self.tick=0
        self.lock=threading.RLock();self.pending=[];self.active=set();self.live=set();self.drone_active=set();self.closed=False
        self.queued=None;self.pitch=PitchEngine(send);self.manual_wheel=0
        self.wake=threading.Event();model.on_change=self.wake.set;self.drone_key=None;self.scheduled=None
        self.active_modes={};self.cycle_id=0;self.recent_onsets=deque(maxlen=3)
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def release(self):
        for c,n in self.active:
            if (c,n) not in self.live and (c,n) not in self.drone_active:self.send('note_off',channel=c,note=n,velocity=0)
        self.active.clear();self.active_modes.clear();self.pending.clear()
    def audition_on(self,c,n,velocity):
        with self.lock:
            self.pitch.wheel[c]=self.manual_wheel;self.pitch.start(c,self.model.pitch_presets[c],time.perf_counter(),self.model.bpm)
            self.live.add((c,n));self.send('note_on',channel=c,note=n,velocity=velocity)
    def audition_off(self,c,n):
        with self.lock:
            if (c,n) in self.live:
                self.live.discard((c,n))
                if (c,n) not in self.active and (c,n) not in self.drone_active:self.send('note_off',channel=c,note=n,velocity=0)
                if not any(ch==c for ch,note in self.live):self.pitch.manual(c,0,time.perf_counter())
                if not any(ch==c for ch,note in self.live|self.active|self.drone_active):self.pitch.reset(c)
    def input_pitch(self,value):
        with self.lock:
            self.manual_wheel=value
            for c in {c for c,n in self.live}:self.pitch.manual(c,value,time.perf_counter())
    def refresh_live_pitch(self,c):
        with self.lock:
            if any(channel==c for channel,n in self.live):self.pitch.start(c,self.model.pitch_presets[c],time.perf_counter(),self.model.bpm)
    def sync_drones(self):
        key=(self.running,self.model.playing,self.model.drone_revision)
        if key==self.drone_key:return
        self.drone_key=key
        desired={(c,n) for c in range(9) if not self.model.muted[c] for n,on in enumerate(self.model.drones[self.model.playing][c]) if on} if self.running else set()
        for c,n in self.drone_active-desired:
            if (c,n) not in self.active|self.live:self.send('note_off',channel=c,note=n,velocity=0)
        for c,n in desired-self.drone_active:
            if (c,n) not in self.active|self.live:self.send('note_on',channel=c,note=n,velocity=self.model.velocity)
        self.drone_active=desired
    def mute(self,c,value):
        with self.lock:
            self.model.set_meta('muted',(c,),value)
            if value:
                for ch,n in list(self.active):
                    if ch==c:
                        self.active.discard((ch,n))
                        if (ch,n) not in self.live|self.drone_active:self.send('note_off',channel=ch,note=n,velocity=0)
                self.pending=[v for v in self.pending if v[1]!=c];heapq.heapify(self.pending)
            self.sync_drones()
    def reconcile_mutes(self):
        with self.lock:
            for c,n in list(self.active):
                if self.model.muted[c]:
                    self.active.discard((c,n))
                    if (c,n) not in self.live|self.drone_active:self.send('note_off',channel=c,note=n,velocity=0)
            self.pending=[v for v in self.pending if not self.model.muted[v[1]]];heapq.heapify(self.pending);self.sync_drones()
    def release_live(self):
        with self.lock:
            for c,n in list(self.live):self.audition_off(c,n)
    def stop(self):
        with self.lock:
            self.running=False;self.send('stop');self.release();self.sync_drones();self.step=-1;self.tick=0;self.paused=False;self.queued=None
            self.scheduled=None;self.recent_onsets.clear();self.wake.set()
            for c in range(9):
                if not any(ch==c for ch,n in self.live):self.pitch.reset(c)
    def toggle(self):
        with self.lock:
            if self.running:self.stop()
            else:
                self.paused=False;self.tick=0;self.next=time.perf_counter();self.running=True;self.send('start');self.wake.set()
    def pause_toggle(self):
        with self.lock:
            self.wake.set()
            if self.running:
                self.remaining=max(0,self.next-time.perf_counter());self.running=False;self.paused=True;self.send('stop');self.release()
            elif self.paused:
                self.next=time.perf_counter()+self.remaining;self.paused=False;self.running=True;self.send('continue')
            else:self.toggle()
    def switch_pattern(self,p,immediate=False):
        with self.lock:
            if self.running and not immediate:self.queued=p;return
            self.release();self.model.playing=p;self.queued=None;self.tick=0;self.step=-1;self.scheduled=None;self.recent_onsets.clear();self.sync_drones();self.wake.set()
    def step_seconds(self,step,length=None):
        length=self.model.lengths[self.model.playing] if length is None else length
        return 60/self.model.bpm/4*(1+(((step+1)%length)%2-step%2)*self.model.swing/300)
    def quantize(self,at):
        """Only retain the last three onsets; predict the next for nearest-step input."""
        if not self.recent_onsets:return self.model.playing,self.cycle_id+1,0
        choices=list(self.recent_onsets)
        onset,p,cycle,step=choices[-1];length=self.model.lengths[p]
        following=(step+1)%length;next_pattern=self.queued if following==0 and self.queued is not None else p
        choices.append((onset+self.step_seconds(step,length),next_pattern,cycle+(following==0),following))
        _,p,cycle,step=min(choices,key=lambda v:abs(v[0]-at))
        return p,cycle,step
    def play_step(self,step,now):
        self.step=step
        if step==0:self.cycle_id+=1
        self.recent_onsets.append((now,self.model.playing,self.cycle_id,step))
        for c,channel in enumerate(self.model.patterns[self.model.playing]):
            if self.model.muted[c]:continue
            chord=[(n,row[step]) for n,row in enumerate(channel) if row[step]]
            if chord:
                first=chord[0][1];self.pitch.start(c,first[2] if len(first)>2 else {},now,self.model.bpm)
            for n,cell in chord:
                if (c,n) in self.drone_active:continue
                mode=cell[2].get('mode','gate') if len(cell)>2 else 'gate'
                tie=mode=='legato' and self.active_modes.get((c,n))=='legato' and (c,n) in self.active
                if (c,n) in self.active:
                    if not tie and (c,n) not in self.live:self.send('note_off',channel=c,note=n,velocity=0)
                    self.pending=[x for x in self.pending if x[1:]!=(c,n)];heapq.heapify(self.pending)
                if not tie:self.send('note_on',channel=c,note=n,velocity=cell[0])
                self.active.add((c,n));self.active_modes[c,n]=mode
                seconds=self.step_seconds(step)*cell[1]/100
                if mode!='gate':
                    length=self.model.lengths[self.model.playing]
                    distance=next((d for d in range(1,length+1) if any(r[(step+d)%length] for r in channel)),length)
                    seconds=max(.001,sum(self.step_seconds((step+d)%length) for d in range(distance))+(.002 if mode=='legato' else -60/self.model.bpm/32))
                heapq.heappush(self.pending,(now+seconds,c,n))
    def release_due(self,now,defer_legato=False):
        delayed=[]
        while self.pending and self.pending[0][0]<=now:
            item=heapq.heappop(self.pending);_,c,n=item
            if defer_legato and self.active_modes.get((c,n))=='legato':delayed.append(item);continue
            if (c,n) not in self.live|self.drone_active:self.send('note_off',channel=c,note=n,velocity=0)
            self.active.discard((c,n));self.active_modes.pop((c,n),None)
        for item in delayed:heapq.heappush(self.pending,item)
    def advance(self,now):
        self.pitch.update(now);self.sync_drones()
        if self.running and now>=self.next:
            self.send('clock')
            if self.tick%6==0:
                if self.tick>0 and (self.tick//6)%self.model.lengths[self.model.playing]==0 and self.queued is not None:self.switch_pattern(self.queued,True)
                step=(self.tick//6)%self.model.lengths[self.model.playing]
                self.scheduled=(self.next+(60/self.model.bpm/4*self.model.swing/300 if step%2 else 0),step)
            self.tick+=1;self.next+=60/self.model.bpm/24
            if now-self.next>.1:self.next=now+60/self.model.bpm/24
        due=self.running and self.scheduled is not None and self.scheduled[0]<=now
        self.release_due(now,due)
        if due:
            onset,step=self.scheduled;self.scheduled=None;self.play_step(step,max(onset,now))
        self.release_due(now)
    def loop(self):
        while not self.closed:
            with self.lock:
                now=time.perf_counter();self.advance(now)
                deadlines=[now+.05]
                if self.running:deadlines.append(self.next)
                if self.scheduled:deadlines.append(self.scheduled[0])
                if self.pending:deadlines.append(self.pending[0][0])
                if self.pitch.moving(now):deadlines.append(now+.004)
                delay=max(.0005,min(deadlines)-time.perf_counter())
                self.wake.clear()
            self.wake.wait(delay)
    def close(self):
        self.stop();self.release_live();self.closed=True;self.wake.set();self.thread.join();self.model.on_change=lambda:None
