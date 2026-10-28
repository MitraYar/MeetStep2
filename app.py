import copy, json, pathlib, queue, sys, tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import mido
from core import Model, Clock, PADS, PADS2, Pickup
from lighting import default_theme, colors, packet, rgb, blend
from shortcuts import DEFAULT_BINDINGS, key_id, migrate_bindings
ROOT=pathlib.Path(__file__).resolve().parent
CONFIG=pathlib.Path.home()/'.meetstep.json'
DEFAULT={'version':2,'ports':['','','','',''],'bindings':DEFAULT_BINDINGS,'theme':default_theme()}
class App:
    def __init__(self,run=True):
        self.root=tk.Tk();self.root.title('MeetStep • SMK 37 Pro');self.root.geometry('1120x730')
        self.held_keys=set();self.key_releases={};self.stroke=None;self.model=Model();self.events=queue.Queue();self.inputs=[];self.outputs=[None]*3
        self.pad_mode=10;self.pad_held=set();self.group=0;self.encoder_attribute=None;self.pickup=Pickup();self.options_window=None
        self.config=json.loads(json.dumps(DEFAULT));self.error='';self.led_cache={};self.led_index=0
        try:
            if CONFIG.exists():
                saved=json.loads(CONFIG.read_text())
                self.config.update(saved);self.config['bindings']=migrate_bindings(saved)
                self.config['version']=2
        except Exception: pass
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
        nav=ttk.Frame(self.root,padding=8);nav.pack(fill='x')
        ttk.Label(nav,text='Channel').pack(side='left')
        self.channel_var=tk.IntVar(value=1)
        channel_box=ttk.Combobox(nav,values=list(range(1,10)),textvariable=self.channel_var,state='readonly',width=3)
        channel_box.pack(side='left');channel_box.bind('<<ComboboxSelected>>',lambda e:self.select_channel(self.channel_var.get()-1))
        ttk.Label(nav,text='Pattern').pack(side='left',padx=8)
        self.pattern_buttons=[]
        for p in range(8):
            button=ttk.Button(nav,text=str(p+1),width=3,command=lambda p=p:self.choose_pattern(p))
            button.pack(side='left');self.pattern_buttons.append(button)
        self.preview_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(nav,text='View only',variable=self.preview_var).pack(side='left',padx=8)
        ttk.Button(nav,text='← Group',command=lambda:self.move_group(-1)).pack(side='left')
        ttk.Button(nav,text='Group →',command=lambda:self.move_group(1)).pack(side='left')
        ttk.Button(nav,text='Global knobs',command=self.global_knobs).pack(side='left')
        editbar=ttk.Frame(self.root,padding=6);editbar.pack(fill='x')
        for label,command in [('Undo · Z',lambda:self.action('undo')),('Redo · X',lambda:self.action('redo')),
                              ('Clear note',lambda:self.clear('note')),('Clear channel',lambda:self.clear('channel')),
                              ('Clear pattern',lambda:self.clear('pattern'))]:
            ttk.Button(editbar,text=label,command=command).pack(side='left',padx=3)
        ttk.Label(editbar,text='Pad layout').pack(side='left',padx=8)
        self.mode_var=tk.IntVar(value=10)
        mode_box=ttk.Combobox(editbar,values=[10,11,13],textvariable=self.mode_var,state='readonly',width=3)
        mode_box.pack(side='left');mode_box.bind('<<ComboboxSelected>>',lambda e:self.set_mode(self.mode_var.get()))
        self.canvas=tk.Canvas(self.root,bg='#101722',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=12)
        self.canvas.bind('<Button-1>',self.click)
        self.canvas.bind('<Button-3>',lambda e:self.click(e,False))
        self.canvas.bind('<B1-Motion>',lambda e:self.drag(e,1))
        self.canvas.bind('<B3-Motion>',lambda e:self.drag(e,3))
        self.root.bind('<ButtonRelease-1>',lambda e:self.end_stroke(1))
        self.root.bind('<ButtonRelease-3>',lambda e:self.end_stroke(3))
        self.root.bind('<FocusOut>',lambda e:self.focus_out())
        self.status=ttk.Label(self.root,padding=10);self.status.pack(fill='x')
        self.root.bind_class('MeetStepKeys','<KeyPress>',self.key)
        self.root.bind_class('MeetStepKeys','<KeyRelease>',self.key_up)
        self.install_key_tag(self.root)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.connect();self.poll()
        if run:self.root.mainloop()
    def cancel_stroke(self):self.model.commit();self.stroke=None
    def install_key_tag(self,widget):
        widget.bindtags(tuple(t for t in widget.bindtags() if t!='MeetStepKeys')[:1]+('MeetStepKeys',)+tuple(t for t in widget.bindtags()[1:] if t!='MeetStepKeys'))
        for child in widget.winfo_children():self.install_key_tag(child)
    def context_change(self):
        self.cancel_stroke();self.pickup.reset()
    def select_channel(self,c):
        self.context_change();self.model.channel=c
    def choose_pattern(self,p,preview=None):
        self.context_change();self.model.pattern=p
        if not (self.preview_var.get() if preview is None else preview):self.clock.switch_pattern(p)
    def set_mode(self,ch):
        if ch!=self.pad_mode:self.pad_held.clear()
        self.pad_mode=ch
    def select_group(self,g,attribute=None):
        self.context_change();self.group=max(0,min(7,g));self.model.page=self.group//2
        if attribute:self.encoder_attribute=attribute
    def move_group(self,d):self.select_group(self.group+d)
    def global_knobs(self):self.context_change();self.encoder_attribute=None
    def clear(self,scope):
        self.context_change();self.model.clear(scope)
    def end_stroke(self,button):
        if self.stroke and self.stroke['button']==button:self.cancel_stroke()
    def range(self,d):
        self.context_change();self.model.base=max(0,min(112,self.model.base+d))
    def send(self,kind,**kw):
        try:
            if self.outputs[0]:
                self.outputs[0].send(mido.Message(kind,**kw))
        except Exception as e:self.error=str(e)
    def connect(self):
        self.clock.stop()
        self.pad_held.clear();self.pickup.reset()
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
        elif name=='options':self.options()
        elif name in ('undo','redo'):
            self.context_change();self.model.history(name=='redo')
        elif name in ('left','right'):self.move_group(-1 if name=='left' else 1)
        else:
            attr,lo,hi={'velocity':('velocity',1,127),'length':('length',15,300),'tempo':('bpm',30,300)}[name]
            val=self.pickup.value(('global',attr),value,getattr(self.model,attr),lo,hi)
            if val is not None:setattr(self.model,attr,val);self.vars[attr].set(val)
    def key(self,e):
        key=key_id(e)
        if e.widget.winfo_class() in ('Entry','TEntry','Text','TSpinbox','Spinbox','TCombobox') and key!='CTRL+VK_BF':return
        action=next((row[0] for row in self.config['bindings'] if row[1] and row[1]==key),None)
        if not action:return
        if e.keycode in self.key_releases:self.root.after_cancel(self.key_releases.pop(e.keycode))
        if e.keycode in self.held_keys:return 'break'
        self.held_keys.add(e.keycode)
        self.action(action)
        return 'break'
    def key_up(self,e):
        def release():
            self.held_keys.discard(e.keycode);self.key_releases.pop(e.keycode,None)
        if e.keycode in self.key_releases:self.root.after_cancel(self.key_releases.pop(e.keycode))
        self.key_releases[e.keycode]=self.root.after_idle(release)
    def focus_out(self):
        self.cancel_stroke();self.held_keys.clear()
        for callback in self.key_releases.values():self.root.after_cancel(callback)
        self.key_releases.clear()
    def midi(self,source,msg):
        if source==1 and msg.type in ('note_on','note_off'):
            if msg.type=='note_off' or msg.velocity==0:
                self.pad_held.discard((msg.channel+1,msg.note));return
            if msg.channel+1 in (10,11,13):
                self.set_mode(msg.channel+1)
                self.pad_held.add((msg.channel+1,msg.note))
        if msg.type=='note_on' and msg.velocity==0:return
        if msg.type not in ('note_on','control_change'):return
        if source==1 and msg.type=='control_change' and msg.channel==5 and 48<=msg.control<=55 and self.encoder_attribute:
            s=self.group*8+msg.control-48;cell=self.model.notes[self.model.selected][s]
            if cell:
                i=0 if self.encoder_attribute=='velocity' else 1;lo,hi=(1,127) if i==0 else (15,300)
                key=(self.model.pattern,self.model.channel,self.model.selected,s,i)
                value=self.pickup.value(key,msg.value,cell[i],lo,hi)
                if value is not None:
                    updated=list(cell);updated[i]=value
                    self.model.set_cell(self.model.pattern,self.model.channel,self.model.selected,s,updated)
            return
        number=msg.note if msg.type=='note_on' else msg.control
        for action,key,src,ch,kind,num in self.config['bindings']:
            if (source,msg.channel+1,msg.type,number)==(src,ch,kind,num):
                if action not in ('play','pause') or msg.type=='note_on' or msg.value>0:self.action(action,msg.velocity if msg.type=='note_on' else msg.value)
                return
        if source==1 and msg.type=='note_on':
            ch=msg.channel+1
            if ch in (10,11,13) and msg.note in PADS2:
                i=PADS2.index(msg.note)
                if ch==13 and i<8:self.select_group(i,'length')
                elif i==8:self.action('pause')
                elif i==15:self.action('undo')
                elif i==7:self.action('redo')
            elif ch==10 and msg.note in PADS:self.model.edit(self.model.selected,self.model.page*16+PADS.index(msg.note))
            elif ch==11 and msg.note in PADS[:8]:
                p=PADS.index(msg.note)
                if (11,PADS[10]) in self.pad_held:self.context_change();self.model.copy_to(p,True)
                elif (11,PADS[9]) in self.pad_held:self.context_change();self.model.copy_to(p)
                else:self.choose_pattern(p,(11,PADS[8]) in self.pad_held)
            elif ch==13 and msg.note in PADS[:8]:self.select_group(PADS.index(msg.note),'velocity')
            elif 0<=msg.channel<=8:
                self.context_change();self.model.channel=msg.channel;self.model.select(msg.note)
    def click(self,e,on=True):
        if self.stroke:return
        w=self.canvas.winfo_width();h=self.canvas.winfo_height()
        if w<=80 or h<=30 or not 30<=e.y<h:return
        row=int((e.y-30)/((h-30)/16))
        n=self.model.base+15-row;self.model.select(n)
        if not 80<=e.x<w:return
        step=int((e.x-80)/((w-80)/16))
        step+=self.model.page*16
        self.model.begin()
        self.stroke={'note':n,'base':self.model.base,'last':step,
                     'context':(self.model.pattern,self.model.channel,self.model.page),
                     'on':on,'button':1 if on else 3,'visited':{step}}
        self.model.edit(n,step,on)
    def drag(self,e,button):
        stroke=self.stroke
        if not stroke or stroke['button']!=button:return
        if self.model.base!=stroke['base'] or self.model.selected!=stroke['note'] or stroke['context']!=(self.model.pattern,self.model.channel,self.model.page):
            self.cancel_stroke();return
        w=self.canvas.winfo_width()
        if w<=80:return
        # Clamp horizontally, ignore vertical motion, and fill skipped columns.
        step=self.model.page*16+max(0,min(15,int((e.x-80)/((w-80)/16))))
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
        self.draw();self.led();self.poll_id=self.root.after(20,self.poll)
    def led(self):
        if not self.outputs[2]:return
        palette=colors(self.model,self.config['theme'],self.pad_mode)
        for _ in range(32):
            i=self.led_index;self.led_index=(i+1)%32
            color=palette[i]
            if self.led_cache.get(i)!=color:
                try:self.outputs[2].send(mido.Message.from_bytes(packet(i,color)));self.led_cache[i]=color
                except Exception as e:self.error=str(e)
                break
    def draw(self):
        c=self.canvas;c.delete('all');w=c.winfo_width();h=c.winfo_height();cw=(w-80)/16;rh=(h-30)/16
        offset=self.model.page*16;theme=self.config['theme']
        for s in range(16):c.create_text(80+(s+.5)*cw,15,text=str(offset+s+1),fill='#68e0ce' if offset+s==self.clock.step else '#94a3b8')
        for r in range(16):
            n=self.model.base+15-r;y=30+r*rh
            label=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][n%12]+str(n//12-2)
            c.create_text(38,y+rh/2,text=f'{label} · {n}',fill='#68e0ce' if n==self.model.selected else '#94a3b8')
            for s in range(16):
                cell=self.model.notes[n][offset+s];x=80+s*cw
                color=blend(theme['low'],theme['high'],cell[0]/127) if cell else theme['empty'][s%theme['empty_length']]
                c.create_rectangle(x+2,y+2,x+cw-2,y+rh-2,fill=color,outline='#dce9f8' if offset+s==self.clock.step and self.model.pattern==self.model.playing else ('#477fff' if (offset+s)//8==self.group else '#28364a'))
                if cell:c.create_text(x+cw/2,y+rh/2,text=str(cell[0]),fill='#ffffff' if sum(rgb(color))<380 else '#102025')
        self.channel_var.set(self.model.channel+1);self.mode_var.set(self.pad_mode)
        for i,b in enumerate(self.pattern_buttons):b.config(text=f'{i+1}'+('▶' if i==self.model.playing else '')+('•' if i==self.model.pattern else ''))
        self.status.config(text=f'View P{self.model.pattern+1} / Play P{self.model.playing+1} · Ch {self.model.channel+1} · Note {self.model.selected} · Steps {offset+1}–{offset+16} · Group {self.group+1} {self.encoder_attribute or "global knobs"} | {self.model.bpm} BPM | '+self.error)
    def options(self):
        self.cancel_stroke()
        if self.options_window and self.options_window.winfo_exists():self.options_window.lift();return
        win=tk.Toplevel(self.root);self.options_window=win;win.title('Options');win.geometry('920x650');book=ttk.Notebook(win);book.pack(fill='both',expand=True)
        ports=ttk.Frame(book,padding=15);bind=ttk.Frame(book,padding=15);book.add(ports,text='MIDI');book.add(bind,text='Shortcuts')
        values=[]
        try:ins=['']+mido.get_input_names();outs=['']+mido.get_output_names()
        except Exception as e:messagebox.showerror('MIDI',str(e));ins=outs=['']
        for i,label in enumerate(['Controller 1 · SMK','Controller 2','Notes / Clock output','Script output (reserved)','RGB output · SMK']):
            ttk.Label(ports,text=label).grid(row=i,column=0,sticky='w');v=tk.StringVar(value=self.config['ports'][i]);values.append(v)
            ttk.Combobox(ports,textvariable=v,values=ins if i<2 else outs,state='readonly',width=55).grid(row=i,column=1,pady=8)
        ttk.Label(ports,text='Each track sends on its MIDI channel (1–9).\nKnobs: absolute CC with pickup. Global mode: CC48 velocity, CC49 length, CC55 BPM.\nChannel 13 selects groups of 8 steps; all 8 knobs then edit that group.').grid(row=5,column=0,columnspan=2,pady=15)
        rows=[]
        for j,title in enumerate(['Action','PC physical key','Controller (0=off)','Channel','MIDI type','Number']):ttk.Label(bind,text=title).grid(row=0,column=j)
        for i,row in enumerate(self.config['bindings']):
            vs=[]
            for j,value in enumerate(row):
                v=tk.StringVar(value=str(value));vs.append(v)
                if j==0:ttk.Label(bind,text=value).grid(row=i+1,column=j)
                else:
                    entry=ttk.Entry(bind,textvariable=v,width=18 if j in (1,4) else 9);entry.grid(row=i+1,column=j,pady=8)
                    if j==1:
                        def capture(event,v=v):
                            if event.keysym in ('Control_L','Control_R','Shift_L','Shift_R','Alt_L','Alt_R'):return 'break'
                            v.set('' if event.keysym in ('BackSpace','Delete') else key_id(event));return 'break'
                        entry.bind('<KeyPress>',capture)
            rows.append(vs)
        ttk.Label(bind,text='Click a PC key field and press the shortcut. Backspace clears it.\nKeys use physical Windows codes: Z / Я, X / Ч, Ctrl + / / Ctrl + .').grid(row=len(rows)+1,column=0,columnspan=6,pady=12)
        interface=ttk.Frame(book,padding=12);book.add(interface,text='Interface')
        theme=copy.deepcopy(self.config['theme']);theme_tabs=ttk.Notebook(interface);theme_tabs.pack(fill='both',expand=True)
        theme_vars={}
        def color_field(parent,label,color,row,column=0):
            v=tk.StringVar(value=color)
            ttk.Label(parent,text=label).grid(row=row,column=column,sticky='w',padx=4,pady=5)
            entry=ttk.Entry(parent,textvariable=v,width=10);entry.grid(row=row,column=column+1)
            button=tk.Button(parent,text='●',bg=color,width=3)
            def choose():
                chosen=colorchooser.askcolor(v.get(),parent=win)[1]
                if chosen:v.set(chosen);button.config(bg=chosen)
            button.config(command=choose);button.grid(row=row,column=column+2,padx=5)
            return v
        for channel in (10,11,13):
            tab=ttk.Frame(theme_tabs,padding=8);theme_tabs.add(tab,text=f'Channel {channel}')
            banks=ttk.Notebook(tab);banks.pack(fill='both',expand=True)
            first=ttk.Frame(banks,padding=10);second=ttk.Frame(banks,padding=10)
            banks.add(first,text='Bank 1');banks.add(second,text='Bank 2')
            if channel==10:
                length=tk.IntVar(value=theme['empty_length']);theme_vars['empty_length']=length
                ttk.Label(first,text='Empty step cycle (1–7)').grid(row=0,column=0)
                ttk.Spinbox(first,from_=1,to=7,textvariable=length,width=5).grid(row=0,column=1)
                theme_vars['empty']=[color_field(first,f'Cycle color {i+1}',color,i+1) for i,color in enumerate(theme['empty'])]
                theme_vars['low']=color_field(first,'Velocity 0',theme['low'],8)
                theme_vars['high']=color_field(first,'Velocity 127',theme['high'],9)
            elif channel==11:
                theme_vars['pattern']=color_field(first,'Pattern color',theme['pattern'],0)
                ttk.Label(first,text='Brightness repeats: 100% → 65% → 35%.\nTop row: patterns 1–8. Bottom row: hold 1 to view, 2 to copy channel, 3 to copy note.').grid(row=1,column=0,columnspan=3,pady=15)
            else:
                theme_vars['encoder_top']=color_field(first,'Top row',theme['encoder_top'],0)
                theme_vars['encoder_bottom']=color_field(first,'Bottom row',theme['encoder_bottom'],1)
                ttk.Label(first,text='Bank 1 top: velocity groups. Bank 2 top: length groups.\nEach group has 8 steps; arrows select groups 1–8.').grid(row=2,column=0,columnspan=3,pady=15)
            theme_vars[f'bank2_{channel}']=[color_field(second,f'Pad {i+1}',color,i%8,0 if i<8 else 3) for i,color in enumerate(theme['bank2'][str(channel)])]
        def apply():
            try:
                b=[]
                for row in rows:
                    a,k,s,c,t,n=[v.get() for v in row];s,c,n=int(s),int(c),int(n)
                    if s not in (0,1,2) or not 1<=c<=16 or not 0<=n<=127 or t not in ('note_on','control_change'):raise ValueError('Invalid binding')
                    b.append([a,k,s,c,t,n])
                keys=[r[1] for r in b if r[1]]
                if len(keys)!=len(set(keys)):raise ValueError('Duplicate PC shortcut')
                names=[v.get() for v in values]
                if len([x for x in names[2:] if x])!=len(set(x for x in names[2:] if x)):raise ValueError('Choose distinct output ports')
                selected_theme={k:theme_vars[k].get() for k in ('empty_length','low','high','pattern','encoder_top','encoder_bottom')}
                if not 1<=selected_theme['empty_length']<=7:raise ValueError('Empty cycle: 1–7')
                selected_theme['empty']=[v.get() for v in theme_vars['empty']]
                selected_theme['bank2']={str(c):[v.get() for v in theme_vars[f'bank2_{c}']] for c in (10,11,13)}
                for color in selected_theme['empty']+[selected_theme[k] for k in ('low','high','pattern','encoder_top','encoder_bottom')]+sum(selected_theme['bank2'].values(),[]):rgb(color)
                updated={'version':2,'ports':names,'bindings':b,'theme':selected_theme}
                CONFIG.write_text(json.dumps(updated,indent=2));ports_changed=names!=self.config['ports'];self.config=updated
                self.pickup.reset();self.led_cache={}
                if ports_changed:self.connect()
            except Exception as e:messagebox.showerror('Options',str(e),parent=win)
        ttk.Button(win,text='Apply',command=apply).pack(side='left',padx=15,pady=10);ttk.Button(win,text='Close',command=win.destroy).pack(side='right',padx=15)
        self.install_key_tag(win)
    def save(self):
        p=filedialog.asksaveasfilename(defaultextension='.json')
        if p:pathlib.Path(p).write_text(json.dumps(self.model.dump()))
    def load(self):
        self.cancel_stroke()
        p=filedialog.askopenfilename()
        if not p:return
        try:
            data=json.loads(pathlib.Path(p).read_text())
            self.clock.stop();self.model.load(data);self.pickup.reset();self.vars['bpm'].set(self.model.bpm)
        except Exception as e:messagebox.showerror('Pattern','Invalid pattern: '+str(e))
    def close(self):
        self.root.after_cancel(self.poll_id)
        self.clock.close()
        for p in self.inputs+[p for p in self.outputs if p]:p.close()
        self.root.destroy()
if __name__=='__main__':App()
