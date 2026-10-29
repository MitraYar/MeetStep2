"""Channel pitch automation. Standard MIDI bends all notes on a channel together."""
import random

class PitchEngine:
    def __init__(self,send,rng=None):
        self.send=send;self.rng=rng or random.Random();self.wheel=[0]*9
        self.curves={};self.last={};self.configured=set()
    def configure(self,c):
        if c in self.configured:return
        for control,value in ((101,0),(100,0),(6,2),(38,0),(101,127),(100,127)):
            self.send('control_change',channel=c,control=control,value=value)
        self.configured.add(c)
    def start(self,c,preset,now,bpm):
        self.configure(c);bend=preset.get('bend',0);micro=preset.get('micro',0)
        amount=self.rng.uniform(25,35)*(1 if bend in (1,2) else -1) if bend else 0
        duration=max(.005,60/bpm/(4 if bend in (1,3) else 12)+self.rng.uniform(-.03,.03)) if bend else 0
        self.curves[c]=(now,duration,amount,micro);self.update(now)
    def update(self,now):
        for c,(start,duration,amount,micro) in list(self.curves.items()):
            cents=micro+amount*max(0,1-(now-start)/duration) if duration else micro
            value=max(-8192,min(8191,round(cents*8192/200)+self.wheel[c]))
            if self.last.get(c)!=value:self.send('pitchwheel',channel=c,pitch=value);self.last[c]=value
    def manual(self,c,value,now):
        self.configure(c);self.wheel[c]=value
        self.curves.setdefault(c,(now,0,0,0));self.update(now)
    def reset(self,c=None):
        for channel in (range(9) if c is None else [c]):
            self.curves.pop(channel,None);self.wheel[channel]=0
            if self.last.get(channel,0)!=0:self.send('pitchwheel',channel=channel,pitch=0)
            self.last[channel]=0
