"""Port recovery off the Tk thread, shared output handles, and bounded CC work."""
import queue
import threading
import time
import mido

def coalesce_controls(events,continuous):
    """Keep anchors, reversals and final values; never merge across a note event."""
    result=[];run=[];key=None;direction=0
    def flush():
        if run:
            result.append(run[0])
            if len(run)>1:result.append(run[-1])
    for event in events:
        source,msg,*_=event
        current=(source,getattr(msg,'channel',-1),getattr(msg,'control',-1))
        if msg.type!='control_change' or current not in continuous:
            flush();run=[];key=None;direction=0;result.append(event);continue
        delta=msg.value-run[-1][1].value if run and current==key else 0
        sign=(delta>0)-(delta<0)
        if current!=key or direction and sign and sign!=direction:
            flush();run=[];direction=0
        run.append(event);key=current
        if sign:direction=sign
    flush();return result

class MidiPorts:
    CHECK_SECONDS=2
    IDLE_REFRESH_SECONDS=120
    def __init__(self,events,backend=mido,now=time.monotonic):
        self.events=events;self.backend=backend;self.now=now;self.notices=queue.Queue()
        self.inputs=[None]*2;self.outputs=[None]*4;self.channel_outputs=[None]*9
        self.input_names=['']*2;self.output_names=['']*4;self.route_names=['']*9
        self.input_times=[0.0]*2;self.sensing=[False]*2;self.busy=[False]*2;self.generations=[0]*2
        self.open_outputs={};self.failed=set();self.reported={};self.config=None;self.revision=0;self.applied=-1
        self.closed=False;self.wake=threading.Event();self.lock=threading.Lock()
        self.thread=threading.Thread(target=self.loop,daemon=True,name='MeetStep MIDI ports');self.thread.start()
    def configure(self,config):
        with self.lock:
            ports=list(config['ports']);routes=list(config.get('channel_outputs',['']*9))
            self.config=(ports,bool(config.get('split_outputs')),routes);self.revision+=1
            for i in range(2):self.generations[i]+=1
        self.wake.set()
    def report(self,key,text):
        if self.reported.get(key)!=text:self.notices.put(('status',text));self.reported[key]=text
    def close_input(self,i):
        port=self.inputs[i];self.inputs[i]=None;self.generations[i]+=1
        if port:
            try:port.close()
            except Exception as exc:self.report(('input_close',i),str(exc))
            self.notices.put(('input_lost',i+1))
    def close_output(self,name):
        port=self.open_outputs.pop(name,None)
        if port:
            # Unpublish before closing so new sends cannot acquire a stale handle.
            for slots in (self.outputs,self.channel_outputs):
                for i,p in enumerate(slots):
                    if p is port:slots[i]=None
            try:port.close()
            except Exception as exc:self.report(('output_close',name),str(exc))
    def receive(self,i,generation,msg):
        if self.closed or generation!=self.generations[i]:return
        self.input_times[i]=self.now()
        if msg.type=='active_sensing':self.sensing[i]=True
        if msg.type not in ('active_sensing','clock'):self.events.put((i+1,msg,time.perf_counter(),generation))
    def fail_output(self,port):
        if port:
            with self.lock:self.failed.add(port)
            self.wake.set()
    def service(self):
        with self.lock:config=self.config;revision=self.revision;failed=self.failed.copy();self.failed.clear()
        if config is None:return
        if revision!=self.applied:
            for i in range(2):self.close_input(i)
            for name in list(self.open_outputs):self.close_output(name)
            ports,split,routes=config;self.input_names=ports[:2];self.output_names=ports[2:]
            self.route_names=[ports[2]]+[routes[c] or ports[2] for c in range(1,9)] if split else [ports[2]]*9
            self.applied=revision
        if not any(self.input_names+self.output_names+self.route_names):return
        now=self.now()
        try:available_in=set(self.backend.get_input_names());available_out=set(self.backend.get_output_names())
        except Exception as exc:self.report('enumerate',f'MIDI device scan: {exc}');return
        for i,name in enumerate(self.input_names):
            if revision!=self.revision:return
            if not name:continue
            port=self.inputs[i];quiet=now-self.input_times[i]
            expired=(self.sensing[i] and quiet>.8) or (not self.busy[i] and quiet>=self.IDLE_REFRESH_SECONDS)
            if port and (name not in available_in or port.closed or expired):self.close_input(i);port=None
            if name not in available_in:self.report(('in',i),f'MIDI input unavailable: {name}');continue
            if port is None:
                try:
                    self.input_times[i]=now;self.sensing[i]=False;generation=self.generations[i]
                    self.inputs[i]=self.backend.open_input(name,callback=lambda msg,i=i,g=generation:self.receive(i,g,msg))
                    if revision!=self.revision:self.close_input(i);return
                    self.report(('in',i),f'MIDI input connected: {name}')
                except Exception as exc:self.report(('in',i),f'MIDI input {name}: {exc}')
        desired=set(self.output_names+self.route_names)-{''}
        for name,port in list(self.open_outputs.items()):
            if name not in desired or name not in available_out or port.closed or port in failed:self.close_output(name)
        ready=[]
        for name in desired:
            if revision!=self.revision:return
            if name in self.open_outputs:continue
            if name not in available_out:self.report(('out',name),f'MIDI output unavailable: {name}');continue
            candidate=None
            try:
                candidate=self.backend.open_output(name)
                if revision!=self.revision:candidate.close();return
                if name in self.route_names:
                    for c in range(9):candidate.send(mido.Message('control_change',channel=c,control=123,value=0))
                self.open_outputs[name]=candidate;ready.append(name)
            except Exception as exc:
                if candidate:
                    try:candidate.close()
                    except Exception:pass
                self.report(('out',name),f'MIDI output {name}: {exc}')
        self.outputs[:]=[self.open_outputs.get(n) for n in self.output_names]
        self.channel_outputs[:]=[self.open_outputs.get(n) for n in self.route_names]
        for name in ready:
            self.notices.put(('output_ready',name));self.report(('out',name),f'MIDI output connected: {name}')
    def loop(self):
        while not self.closed:
            self.wake.clear()
            try:self.service()
            except Exception as exc:self.report('worker',f'MIDI recovery: {exc}')
            self.wake.wait(self.CHECK_SECONDS)
        for i in range(2):self.close_input(i)
        for name in list(self.open_outputs):self.close_output(name)
    def close(self):
        self.closed=True;self.wake.set();self.thread.join(timeout=3)
