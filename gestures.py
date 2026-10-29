"""Row-locked drawing, relative value gestures and sticky selection mode."""
import time

class GridGestures:
    def __init__(self,app):self.a=app;self.header_anchor=None
    def hit(self,e):
        a=self.a;w,h=a.canvas.winfo_width(),a.canvas.winfo_height()
        if w<=80 or h<=30:return None
        row=max(0,min(15,int((e.y-30)/((h-30)/16))))
        n=a.model.base+15-row;s=a.model.page*16+max(0,min(15,int((e.x-80)/((w-80)/16))))
        return n,s,30+(row+.5)*(h-30)/16,(h-30)/16
    def header(self,n,state):
        a=self.a;e=a.editor
        if state&1 and self.header_anchor is not None:
            cells={(note,s) for note in range(min(n,self.header_anchor),max(n,self.header_anchor)+1) for s in range(64)}
            e.selection|=cells
        else:
            cells={(n,s) for s in range(64)}
            if state&4:
                if cells<=e.selection:e.selection-=cells
                else:e.selection|=cells
            else:e.selection=cells
            self.header_anchor=n
        if e.selection:e.step=min(s for note,s in e.selection);a.model.select(max(note for note,s in e.selection))
        a.reset_faders()
    def press(self,event,on=True):
        a=self.a;m=a.model;e=a.editor
        if a.stroke:return
        a.canvas.focus_set();hit=self.hit(event)
        if not hit or not 30<=event.y<a.canvas.winfo_height():return
        n,s,center,rh=hit;state=getattr(event,'state',0);m.select(n)
        if event.x<80:
            if not on:m.set_meta('drones',(m.pattern,m.channel,n),False);return
            if state&5 or e.selection:self.header(n,state);return
            a.stroke={'kind':'header','note':n,'state':state,'start_time':time.monotonic(),'button':1,'fired':False};return
        if a.select_mode and not on:e.reset_selection();return
        e.step=s;a.reset_faders()
        if state&1 or a.select_mode:
            e.anchor=(n,s);e.reset_selection();e.anchor=(n,s)
            a.stroke={'kind':'select_rect' if on else 'erase_rect','start':(n,s),'end':(n,s),'button':1 if on else 3,'moved':False}
            if not a.select_mode:e.rectangle((n,s),(n,s))
            return
        if state&4 and on:
            cell=(n,s)
            if cell in e.selection:e.selection.remove(cell)
            else:e.selection.add(cell)
            return
        e.reset_selection();m.begin()
        if not on:m.set_meta('drones',(m.pattern,m.channel,n),False)
        a.stroke={'kind':'paint' if a.paint_mode else 'draw','note':n,'base':m.base,'last':s,'center':center,'rh':rh,
                  'context':(m.pattern,m.channel,m.page),'on':on,'button':1 if on else 3,'visited':set(),
                  'baseline':{},'absolute':not on,'last_y':event.y}
        self.move(event,1 if on else 3)
    def move(self,event,button):
        a=self.a;m=a.model;e=a.editor;stroke=a.stroke
        if not stroke or stroke['button']!=button:return
        hit=self.hit(event)
        if not hit:return
        n,s,_,_=hit
        if stroke['kind']=='header':return
        if stroke['kind'] in ('select_rect','erase_rect'):
            stroke['end']=(n,s);stroke['moved']|=stroke['end']!=stroke['start']
            if stroke['moved'] or not a.select_mode:e.rectangle(stroke['start'],stroke['end'])
            return
        if m.base!=stroke['base'] or stroke['context']!=(m.pattern,m.channel,m.page):a.cancel_stroke();return
        n=stroke['note'];stroke['last_y']=event.y
        for step in range(min(stroke['last'],s),max(stroke['last'],s)+1):
            if stroke['kind']=='paint':
                cell=m.notes[n][step]
                if not cell:continue
                index=0 if a.paint_mode=='velocity' else 1;lo,hi=(1,127) if index==0 else (15,300)
                old=stroke['baseline'].setdefault((step,index),cell[index]);delta=(stroke['center']-event.y)/stroke['rh']
                factor=2**(max(-10,min(10,(max(0,abs(delta)-.5)*(1 if delta>0 else -1))*.35)))
                value=getattr(m,a.paint_mode) if stroke['absolute'] else round(old*factor)
                updated=list(cell);updated[index]=max(lo,min(hi,value));m.set_cell(m.pattern,m.channel,n,step,updated)
                if index:a.gate_until=time.monotonic()+1
            elif step not in stroke['visited']:e.edit(n,step,stroke['on'])
            stroke['visited'].add(step)
        stroke['last']=s;e.step=s
    def poll(self):
        a=self.a;stroke=a.stroke
        if stroke and stroke['kind']=='header' and not stroke['fired'] and time.monotonic()-stroke['start_time']>=.5:
            self.header(stroke['note'],stroke['state']);stroke['fired']=True
    def release(self,button):
        a=self.a;stroke=a.stroke
        if not stroke or stroke['button']!=button:return
        if stroke['kind']=='erase_rect':a.editor.erase_rectangle(stroke['start'],stroke['end'])
        if stroke['kind']=='select_rect' and a.select_mode and not stroke['moved']:a.editor.reset_selection()
        a.cancel_stroke()
