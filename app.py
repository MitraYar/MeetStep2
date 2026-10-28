import json, pathlib, queue, sys, tkinter as tk
from tkinter import ttk, messagebox, filedialog
import mido
from core import Model, Clock, PADS
ROOT=pathlib.Path(__file__).resolve().parent
CONFIG=pathlib.Path.home()/'.meetstep.json'
DEFAULT={'ports':['','','','',''],'channel':10,'bindings':[
 ['play','',1,10,'note_on',52],['pause','space',0,1,'note_on',0],['velocity','',1,6,'control_change',48],
 ['length','',1,6,'control_change',49],['tempo','',1,6,'control_change',55]]}
class App:
    def __init__(self):
        self.root=tk.Tk();self.root.title('MeetStep • SMK 37 Pro');self.root.geometry('1120x730')
        self.held_keys=set();self.key_releases={};self.stroke=None;self.model=Model();self.events=queue.Queue();self.inputs=[];self.outputs=[None]*3
        self.config=json.loads(json.dumps(DEFAULT));self.error='';self.led_cache={};self.led_index=0
        try:
            if CONFIG.exists():
                self.config=json.loads(CONFIG.read_text())
                if not any(row[0]=='pause' for row in self.config['bindings']):
                    for row in self.config['bindings']:
                        if row[0]=='play' and row[1]=='space':row[1]=''
                    self.config['bindings'].append(['pause','space',0,1,'note_on',0])
        except Exception: pass
        self.packets=json.loads((ROOT/'led_packets.json').read_text())
        self.clock=Clock(self.model,self.send)
        bar=ttk.Frame(self.root,padding=12);bar.pack(fill='x')
        ttk.Label(bar,text='MEETSTEP',font=('Segoe UI',20,'bold')).pack(side='left')
        ttk.Button(bar,text='Play / Pause',command=self.clock.pause_toggle).pack(side='left',padx=10)
        ttk.Button(bar,text='Stop',command=self.clock.stop).pack(side='left')
        ttk.Button(bar,text='Options',command=self.options).pack(side='right')
        ttk.Button(bar,text='Save pattern',command=self.save).pack(side='right')
        ttk.Button(bar,text='Load pattern',command=self.load).pack(side='right')
        self.vars={}
        controls=ttk.Frame(self.root,padding=10);controls.pack(fill='x')
        for name,lo,hi in [('velocity',1,127),('length',15,300),('bpm',30,300)]:
            ttk.Label(controls,text=name).pack(side='left');v=tk.DoubleVar(value=getattr(self.model,name));self.vars[name]=v
            ttk.Scale(controls,from_=lo,to=hi,variable=v,command=lambda val,n=name:setattr(self.model,n,round(float(val)))).pack(side='left',padx=10)
        ttk.Button(controls,text='−16',command=lambda:self.range(-16)).pack(side='left')
        ttk.Button(controls,text='+16',command=lambda:self.range(16)).pack(side='left')
        self.canvas=tk.Canvas(self.root,bg='#101722',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=12)
        self.canvas.bind('<Button-1>',self.click)
        self.canvas.bind('<Button-3>',lambda e:self.click(e,False))
        self.canvas.bind('<B1-Motion>',lambda e:self.drag(e,1))
        self.canvas.bind('<B3-Motion>',lambda e:self.drag(e,3))
        self.root.bind('<ButtonRelease-1>',lambda e:self.end_stroke(1))
        self.root.bind('<ButtonRelease-3>',lambda e:self.end_stroke(3))
        self.root.bind('<FocusOut>',lambda e:self.focus_out())
        self.status=ttk.Label(self.root,padding=10);self.status.pack(fill='x')
        self.root.bind('<KeyPress>',self.key);self.root.bind('<KeyRelease>',self.key_up);self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.connect();self.poll();self.root.mainloop()
    def cancel_stroke(self):self.stroke=None
    def end_stroke(self,button):
        if self.stroke and self.stroke['button']==button:self.cancel_stroke()
    def range(self,d):
        self.cancel_stroke();self.model.base=max(0,min(112,self.model.base+d))
    def send(self,kind,**kw):
        try:
            if self.outputs[0]:
                if kind in ('note_on','note_off'):kw['channel']=self.config['channel']-1
                self.outputs[0].send(mido.Message(kind,**kw))
        except Exception as e:self.error=str(e)
    def connect(self):
        self.clock.stop()
        for p in self.inputs+[p for p in self.outputs if p]:p.close()
        self.inputs=[];self.outputs=[None]*3;self.led_cache={}
        try:
            for i,name in enumerate(self.config['ports'][:2]):
                if name:self.inputs.append(mido.open_input(name,callback=lambda msg,source=i+1:self.events.put((source,msg))))
            for i,name in enumerate(self.config['ports'][2:]):
                if name:self.outputs[i]=mido.open_output(name)
            self.error=''
        except Exception as e:self.error=str(e)
    def action(self,name,value=127):
        if name=='play':self.clock.toggle()
        elif name=='pause':self.clock.pause_toggle()
        else:
            attr,lo,hi={'velocity':('velocity',1,127),'length':('length',15,300),'tempo':('bpm',30,300)}[name]
            val=round(lo+(hi-lo)*value/127);setattr(self.model,attr,val);self.vars[attr].set(val)
    def key(self,e):
        if e.widget is not self.root and e.widget is not self.canvas:return
        if e.keysym in self.key_releases:
            self.root.after_cancel(self.key_releases.pop(e.keysym))
        if e.keysym in self.held_keys:return
        self.held_keys.add(e.keysym)
        for action,key,*_ in self.config['bindings']:
            if key and e.keysym==key:self.action(action)
    def key_up(self,e):
        def release():
            self.held_keys.discard(e.keysym);self.key_releases.pop(e.keysym,None)
        self.key_releases[e.keysym]=self.root.after_idle(release)
    def focus_out(self):
        self.cancel_stroke();self.held_keys.clear()
        for callback in self.key_releases.values():self.root.after_cancel(callback)
        self.key_releases.clear()
    def midi(self,source,msg):
        if msg.type=='note_on' and msg.velocity==0:return
        if msg.type not in ('note_on','control_change'):return
        number=msg.note if msg.type=='note_on' else msg.control
        for action,key,src,ch,kind,num in self.config['bindings']:
            if (source,msg.channel+1,msg.type,number)==(src,ch,kind,num):
                if action not in ('play','pause') or msg.type=='note_on' or msg.value>0:self.action(action,msg.velocity if msg.type=='note_on' else msg.value)
                return
        if source==1 and msg.type=='note_on':
            if msg.channel==9 and msg.note in PADS:self.model.edit(self.model.selected,PADS.index(msg.note))
            elif 0<=msg.channel<=8:
                self.cancel_stroke();self.model.select(msg.note)
    def click(self,e,on=True):
        if self.stroke:return
        w=self.canvas.winfo_width();h=self.canvas.winfo_height()
        if w<=80 or h<=30 or not 30<=e.y<h:return
        row=int((e.y-30)/((h-30)/16))
        n=self.model.base+15-row;self.model.select(n)
        if not 80<=e.x<w:return
        step=int((e.x-80)/((w-80)/16))
        self.stroke={'note':n,'base':self.model.base,'last':step,
                     'on':on,'button':1 if on else 3,'visited':{step}}
        self.model.edit(n,step,on)
    def drag(self,e,button):
        stroke=self.stroke
        if not stroke or stroke['button']!=button:return
        if self.model.base!=stroke['base'] or self.model.selected!=stroke['note']:
            self.cancel_stroke();return
        w=self.canvas.winfo_width()
        if w<=80:return
        # Clamp horizontally, ignore vertical motion, and fill skipped columns.
        step=max(0,min(15,int((e.x-80)/((w-80)/16))))
        for s in range(min(stroke['last'],step),max(stroke['last'],step)+1):
            if s not in stroke['visited']:
                self.model.edit(stroke['note'],s,stroke['on'])
                stroke['visited'].add(s)
        stroke['last']=step
    def poll(self):
        for _ in range(256):
            try:source,msg=self.events.get_nowait()
            except queue.Empty:break
            self.midi(source,msg)
        self.draw();self.led();self.root.after(20,self.poll)
    def led(self):
        # Exact captured red/white packets; physical index mapping requires hardware validation.
        if not self.outputs[2]:return
        for _ in range(32):
            i=self.led_index;self.led_index=(i+1)%32
            white=bool(self.model.notes[self.model.selected][i]) if i<16 else (i==24 and self.clock.running)
            if self.led_cache.get(i)!=white:
                try:self.outputs[2].send(mido.Message.from_bytes(self.packets[i+32*white]));self.led_cache[i]=white
                except Exception as e:self.error=str(e)
                break
    def draw(self):
        c=self.canvas;c.delete('all');w=c.winfo_width();h=c.winfo_height();cw=(w-80)/16;rh=(h-30)/16
        for s in range(16):c.create_text(80+(s+.5)*cw,15,text=str(s+1),fill='#68e0ce' if s==self.clock.step else '#94a3b8')
        for r in range(16):
            n=self.model.base+15-r;y=30+r*rh
            label=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][n%12]+str(n//12-2)
            c.create_text(38,y+rh/2,text=f'{label} · {n}',fill='#68e0ce' if n==self.model.selected else '#94a3b8')
            for s in range(16):
                cell=self.model.notes[n][s];x=80+s*cw
                c.create_rectangle(x+2,y+2,x+cw-2,y+rh-2,fill='#39bda7' if cell else ('#27364b' if n==self.model.selected else '#1b2636'),outline='#dce9f8' if s==self.clock.step else '')
                if cell:c.create_text(x+cw/2,y+rh/2,text=str(cell[0]),fill='#102025')
        self.status.config(text=f'Note {self.model.selected} | Velocity {self.model.velocity} | Length {self.model.length}% | {self.model.bpm} BPM | '+(self.error or 'Left click: set • Right click: erase • Clock: 24 PPQN'))
    def options(self):
        self.cancel_stroke()
        win=tk.Toplevel(self.root);win.title('Options');win.geometry('820x500');book=ttk.Notebook(win);book.pack(fill='both',expand=True)
        ports=ttk.Frame(book,padding=15);bind=ttk.Frame(book,padding=15);book.add(ports,text='MIDI');book.add(bind,text='Shortcuts')
        values=[]
        try:ins=['']+mido.get_input_names();outs=['']+mido.get_output_names()
        except Exception as e:messagebox.showerror('MIDI',str(e));ins=outs=['']
        for i,label in enumerate(['Controller 1 · SMK','Controller 2','Notes / Clock output','Script output (reserved)','RGB output · SMK']):
            ttk.Label(ports,text=label).grid(row=i,column=0,sticky='w');v=tk.StringVar(value=self.config['ports'][i]);values.append(v)
            ttk.Combobox(ports,textvariable=v,values=ins if i<2 else outs,state='readonly',width=55).grid(row=i,column=1,pady=8)
        ch=tk.IntVar(value=self.config['channel']);ttk.Label(ports,text='Output channel').grid(row=5,column=0);ttk.Spinbox(ports,from_=1,to=16,textvariable=ch).grid(row=5,column=1)
        rows=[]
        for j,title in enumerate(['Action','PC keysym','Controller (0=off)','Channel','MIDI type','Number']):ttk.Label(bind,text=title).grid(row=0,column=j)
        for i,row in enumerate(self.config['bindings']):
            vs=[]
            for j,value in enumerate(row):
                v=tk.StringVar(value=str(value));vs.append(v)
                if j==0:ttk.Label(bind,text=value).grid(row=i+1,column=j)
                else:ttk.Entry(bind,textvariable=v,width=15 if j in (1,4) else 9).grid(row=i+1,column=j,pady=8)
            rows.append(vs)
        def apply():
            try:
                b=[]
                for row in rows:
                    a,k,s,c,t,n=[v.get() for v in row];s,c,n=int(s),int(c),int(n)
                    if s not in (0,1,2) or not 1<=c<=16 or not 0<=n<=127 or t not in ('note_on','control_change'):raise ValueError('Invalid binding')
                    b.append([a,k,s,c,t,n])
                if not 1<=ch.get()<=16:raise ValueError('Channel: 1–16')
                names=[v.get() for v in values]
                if len([x for x in names[2:] if x])!=len(set(x for x in names[2:] if x)):raise ValueError('Choose distinct output ports')
                self.config={'ports':names,'channel':ch.get(),'bindings':b};CONFIG.write_text(json.dumps(self.config,indent=2));self.connect()
            except Exception as e:messagebox.showerror('Options',str(e),parent=win)
        ttk.Button(win,text='Apply',command=apply).pack(side='left',padx=15,pady=10);ttk.Button(win,text='Close',command=win.destroy).pack(side='right',padx=15)
    def save(self):
        p=filedialog.asksaveasfilename(defaultextension='.json')
        if p:pathlib.Path(p).write_text(json.dumps(self.model.notes))
    def load(self):
        self.cancel_stroke()
        p=filedialog.askopenfilename()
        if not p:return
        try:
            data=json.loads(pathlib.Path(p).read_text())
            assert len(data)==128 and all(len(r)==16 for r in data)
            assert all(c is None or (len(c)==2 and 1<=c[0]<=127 and 15<=c[1]<=300) for r in data for c in r)
            self.clock.stop();self.model.notes=data
        except Exception as e:messagebox.showerror('Pattern','Invalid pattern: '+str(e))
    def close(self):
        self.clock.close()
        for p in self.inputs+[p for p in self.outputs if p]:p.close()
        self.root.destroy()
if __name__=='__main__':App()
