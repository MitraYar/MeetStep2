"""Configurable per-channel pitch envelopes, with a standard ±2-semitone RPN."""
import math
import random
import copy

def defaults():
    return {'micro':[{'cents':c,'ms':0} for c in (-68,22,-22,-50)],
            'approach':[{'start':30 if i<2 else -30,'random':5,'time':'1/16' if i%2==0 else '1/48','curve':50} for i in range(4)]}

def duration(value,bpm):
    text=str(value).strip().replace('\\','/')
    if '/' in text:
        numerator,denominator=text.split('/');n,d=float(numerator),float(denominator)
        if n<=0 or d<=0:raise ValueError('Note duration must be positive')
        seconds=240/bpm*n/d
    else:seconds=float(text)/1000
    if not math.isfinite(seconds) or not 0<=seconds<=120:raise ValueError('Time must be 0–120000 ms or a fraction such as 1/16')
    return seconds

def validate_settings(data):
    data=copy.deepcopy(data)
    if not isinstance(data,dict) or len(data.get('micro',[]))!=4 or len(data.get('approach',[]))!=4:raise ValueError('Expected four microtones and four approaches')
    for v in data['micro']:
        v['cents']=float(v['cents']);v['ms']=float(v['ms'])
        if not -200<=float(v['cents'])<=200 or not 0<=float(v['ms'])<=120000:raise ValueError('Microtone: ±200 cents, 0–120000 ms')
    for v in data['approach']:
        for key in ('start','random','curve'):v[key]=float(v[key])
        if not -200<=float(v['start'])<=200 or not 0<=float(v['random'])<=200 or not 0<=float(v['curve'])<=100:raise ValueError('Approach: ±200 cents, random 0–200, curve 0–100')
        duration(v['time'],30)
    return data

def validate_preset(meta):
    if not isinstance(meta,dict):raise ValueError('Invalid cell metadata')
    if any(not isinstance(meta.get(key,0),(int,float)) for key in ('micro','micro_ms')):raise ValueError('Pitch values must be numeric')
    if not -200<=float(meta.get('micro',0))<=200 or meta.get('bend',0) not in range(5):raise ValueError('Invalid pitch data')
    if not 0<=float(meta.get('micro_ms',0))<=120000 or meta.get('mode','gate') not in ('gate','legato','nonlegato'):raise ValueError('Invalid cell mode')
    if 'approach' in meta:
        if not isinstance(meta['approach'],dict) or any(not isinstance(meta['approach'].get(k),(int,float)) for k in ('start','random','curve')):raise ValueError('Invalid stored approach')
        settings=defaults();settings['approach'][0]=meta['approach'];validate_settings(settings)

class PitchEngine:
    def __init__(self,send,rng=None):
        self.send=send;self.rng=rng or random.Random();self.wheel=[0]*9
        self.curves={};self.last={};self.configured=set()
    def configure(self,c):
        if c in self.configured:return
        for control,value in ((101,0),(100,0),(6,2),(38,0),(101,127),(100,127)):
            self.send('control_change',channel=c,control=control,value=value)
        self.configured.add(c)
    def cents(self,c,now):
        v=self.curves.get(c)
        if not v:return 0
        elapsed=max(0,now-v['start'])
        t=min(1,elapsed/v['micro_time']) if v['micro_time'] else 1
        micro=v['from']+(v['micro']-v['from'])*t
        progress=min(1,elapsed/v['duration']) if v['duration'] else 1
        return micro+v['amount']*(1-progress**v['power'])
    def start(self,c,preset,now,bpm):
        self.configure(c);bend=preset.get('bend',0);old=self.cents(c,now)
        approach=preset.get('approach',defaults()['approach'][bend-1]) if bend else None
        amount=approach['start']+self.rng.uniform(-approach['random'],approach['random']) if approach else 0
        seconds=max(.001,duration(approach['time'],bpm)+self.rng.uniform(-.03,.03)) if approach else 0
        self.curves[c]={'start':now,'duration':seconds,'amount':amount,'micro':preset.get('micro',0),'from':old,
                        'micro_time':preset.get('micro_ms',0)/1000,'power':2**((50-approach['curve'])/16.6667) if approach else 1}
        self.update(now)
    def moving(self,now):
        return any(now<v['start']+max(v['duration'],v['micro_time']) for v in list(self.curves.values()))
    def update(self,now):
        for c in tuple(self.curves):
            value=max(-8192,min(8191,round(self.cents(c,now)*8192/200)+self.wheel[c]))
            if self.last.get(c)!=value:self.send('pitchwheel',channel=c,pitch=value);self.last[c]=value
    def manual(self,c,value,now):
        self.configure(c);self.wheel[c]=value
        if c not in self.curves:self.start(c,{},now,120)
        else:self.update(now)
    def reset(self,c=None):
        for channel in (range(9) if c is None else [c]):
            self.curves.pop(channel,None);self.wheel[channel]=0
            if self.last.get(channel,0)!=0:self.send('pitchwheel',channel=channel,pitch=0)
            self.last[channel]=0
