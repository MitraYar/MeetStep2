import copy
import json
import re
import tkinter as tk
from tkinter import ttk,colorchooser,messagebox,filedialog
from shortcuts import action_label,pretty_key,key_id,migrate_bindings,pad_label,action_order,DEFAULT_BINDINGS
from lighting import merge_theme,rgb
from core import PADS,PADS2
from ui_helpers import Tooltip,tooltips

def normalize_settings(data):
    if not isinstance(data,dict):raise ValueError('Expected settings object')
    result=copy.deepcopy(data);result['bindings']=migrate_bindings(data);result['version']=4
    ports=list(result.get('ports',['']*6));ports+=['']*(6-len(ports))
    if len(ports)!=6 or any(not isinstance(p,str) for p in ports):raise ValueError('Expected 2 inputs and 4 outputs')
    result['ports']=ports;result['theme']=merge_theme(result.get('theme',{}))
    names=result.setdefault('controller_names',['SMK 37 Pro','Controller 2'])
    if len(names)!=2 or any(not isinstance(n,str) for n in names):raise ValueError('Controller names')
    aliases=result.setdefault('binding_names',{})
    if not isinstance(aliases,dict) or any(not isinstance(v,str) for v in aliases.values()):raise ValueError('Binding names')
    keys=[]
    for row in result['bindings']:
        if len(row)!=6:raise ValueError('Invalid binding')
        action,key,src,ch,kind,num=row
        if action not in {r[0] for r in DEFAULT_BINDINGS}|{'play'}:raise ValueError('Unknown action: '+str(action))
        if not isinstance(key,str) or any(type(v)!=int for v in (src,ch,num)):raise ValueError('Invalid binding values')
        if key and not re.fullmatch(r'(?:(?:CTRL|ALT|SHIFT)\+)*VK_[0-9A-F]{2}',key):raise ValueError('Invalid physical key binding')
        if src not in (0,1,2) or not 1<=ch<=16 or kind not in ('note_on','control_change') or not 0<=num<=127:raise ValueError('Invalid MIDI binding')
        if key:keys.append(key)
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate PC shortcut')
    t=result['theme']
    if t['ui'] not in ('Dark','Light','Legacy light') or not 1<=t['empty_length']<=7 or not 0<=t['grid_tint']<=100:raise ValueError('Invalid interface setting')
    if len(t['empty'])!=7:raise ValueError('Expected 7 cycle colors')
    for color in t['empty']+[t['low'],t['high'],t['pattern']]:rgb(color)
    for bank in ('bank1','bank2'):
        for ch in range(10,17):
            if len(t[bank][str(ch)])!=16:raise ValueError('Expected 16 pad colors')
            for color in t[bank][str(ch)]:rgb(color)
    return result

class SettingsDialog:
    def __init__(self,app):
        self.app=app;self.rows=sorted(copy.deepcopy(app.config['bindings']),key=lambda r:action_order(r[0]));self.names=dict(app.config.get('binding_names',{}));self.learn=None;self.current=None
        self.win=tk.Toplevel(app.root);app.options_window=self.win;self.win.title('MeetStep · Options')
        self.win.geometry(f'{min(1080,self.win.winfo_screenwidth()-40)}x{min(740,self.win.winfo_screenheight()-70)}');self.win.minsize(960,620)
        self.book=ttk.Notebook(self.win);self.book.pack(fill='both',expand=True,padx=10,pady=10)
        self.midi=ttk.Frame(self.book,padding=12);self.shortcuts=ttk.Frame(self.book,padding=12);self.interface=ttk.Frame(self.book,padding=12)
        for frame,name in ((self.midi,'MIDI'),(self.shortcuts,'Shortcuts'),(self.interface,'Interface')):self.book.add(frame,text=name)
        self.book.select(min(app.last_options_tab,2));self.book.bind('<<NotebookTabChanged>>',lambda e:setattr(app,'last_options_tab',self.book.index('current')))
        self.ports=[];self.controller_names=[]
        try:inputs=['']+app.mido_inputs();outputs=['']+app.mido_outputs()
        except Exception:inputs=outputs=['']
        for i,label in enumerate(['Controller 1 input','Controller 2 input','Sequence / audition output','Script output (reserved)','SMK RGB output','Pads 14–16 output']):
            ttk.Label(self.midi,text=label).grid(row=i,column=0,sticky='w',pady=9)
            v=tk.StringVar(value=app.config['ports'][i]);self.ports.append(v)
            ttk.Combobox(self.midi,textvariable=v,values=inputs if i<2 else outputs,width=65,state='readonly').grid(row=i,column=1)
        for i,name in enumerate(app.config['controller_names']):
            ttk.Label(self.midi,text=f'Controller {i+1} name').grid(row=6+i,column=0,sticky='w',pady=8)
            v=tk.StringVar(value=name);self.controller_names.append(v);ttk.Entry(self.midi,textvariable=v,width=40).grid(row=6+i,column=1,sticky='w')
        ttk.Label(self.midi,text='Bank 1 knobs: CC48–55 velocity. Bank 2: CC56–63 gate, MIDI channel 6.\nUse MIDI Learn on a knob action if your preset sends another CC/channel.\nFaders: 1 velocity / 2 gate / 4 BPM. Pitch range: ±2 semitones.').grid(row=8,column=0,columnspan=2,pady=15,sticky='w')
        columns=('action','code','key','controller','channel','type','number')
        self.tree=ttk.Treeview(self.shortcuts,columns=columns,show='headings',height=13)
        for col,title,width in zip(columns,['Action','Physical code','Key','Controller','Ch','MIDI','No.'],[280,125,110,135,35,100,40]):
            self.tree.heading(col,text=title);self.tree.column(col,width=width,stretch=col=='action')
        scroll=ttk.Scrollbar(self.shortcuts,command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0,column=0,columnspan=7,sticky='nsew');scroll.grid(row=0,column=7,sticky='ns');self.shortcuts.rowconfigure(0,weight=1);self.shortcuts.columnconfigure(0,weight=1)
        self.fields=[]
        for i,(label,value) in enumerate(zip(['PC binding','Controller #','Channel','Type','Number','Controller name'],['','0','1','note_on','0',''])):
            ttk.Label(self.shortcuts,text=label).grid(row=1,column=i,sticky='w',pady=(12,3))
            v=tk.StringVar(value=value);self.fields.append(v);entry=ttk.Entry(self.shortcuts,textvariable=v,width=16 if i in (0,3,5) else 9);entry.grid(row=2,column=i,padx=3,sticky='ew')
            if i==0:
                def capture(e):
                    if e.keysym in ('Control_L','Control_R','Shift_L','Shift_R','Alt_L','Alt_R'):return 'break'
                    self.fields[0].set('' if e.keysym in ('BackSpace','Delete') else key_id(e));return 'break'
                entry.bind('<KeyPress>',capture)
        self.pretty=tk.StringVar();self.fields[0].trace_add('write',lambda *args:self.pretty.set(pretty_key(self.fields[0].get())))
        ttk.Label(self.shortcuts,textvariable=self.pretty).grid(row=3,column=0,sticky='w')
        ttk.Button(self.shortcuts,text='Update binding',command=self.update_row).grid(row=3,column=1,columnspan=2,pady=10)
        self.learn_text=tk.StringVar(value='MIDI Learn');ttk.Button(self.shortcuts,textvariable=self.learn_text,command=self.start_learn).grid(row=3,column=3)
        ttk.Button(self.shortcuts,text='Clear MIDI',command=self.clear_midi).grid(row=3,column=4)
        self.tree.bind('<<TreeviewSelect>>',self.select_row);self.refresh()
        self.theme=merge_theme(app.config['theme']);self.theme_vars={};self.dynamic_pads=[]
        top=ttk.Frame(self.interface);top.pack(fill='x')
        ttk.Label(top,text='Appearance').pack(side='left');self.appearance=tk.StringVar(value=self.theme['ui'])
        ttk.Combobox(top,textvariable=self.appearance,values=['Dark','Light','Legacy light'],state='readonly',width=16).pack(side='left',padx=10)
        ttk.Label(top,text='PC grid tint').pack(side='left');self.tint=tk.DoubleVar(value=self.theme['grid_tint']);self.tint_label=tk.StringVar(value=f'{self.tint.get():.0f}%')
        ttk.Scale(top,from_=0,to=100,variable=self.tint,command=lambda v:self.tint_label.set(f'{float(v):.0f}%')).pack(side='left',fill='x',expand=True)
        ttk.Label(top,textvariable=self.tint_label,width=5).pack(side='left')
        channels=ttk.Notebook(self.interface);channels.pack(fill='both',expand=True,pady=10)
        self.cycle=tk.IntVar(value=self.theme['empty_length'])
        for ch in range(10,17):
            frame=ttk.Frame(channels,padding=8);channels.add(frame,text=f'Ch {ch}')
            banks=ttk.Notebook(frame);banks.pack(fill='both',expand=True)
            for bank in (1,2):
                panel=ttk.Frame(banks,padding=10);banks.add(panel,text=f'Bank {bank}')
                for i in range(16):
                    action=next((r[0] for r in self.rows if r[2:]==[1,ch,'note_on',(PADS if bank==1 else PADS2)[i]]),None)
                    hint=action_label(action) if action else 'Unassigned'
                    assigned=bool(action) and 'Unassigned' not in hint
                    color=self.theme[f'bank{bank}'][str(ch)][i]
                    button=tk.Button(panel,text=f'{i+1}'+(' ★' if assigned else ''),bg=color,fg='white',width=7,height=2)
                    button.grid(row=i//8,column=i%8,padx=3,pady=5)
                    def choose(b=button,c=ch,k=bank,index=i):
                        picked=colorchooser.askcolor(self.theme[f'bank{k}'][str(c)][index],parent=self.win)[1]
                        if picked:self.theme[f'bank{k}'][str(c)][index]=picked;b.config(bg=picked)
                    button.configure(command=choose);Tooltip(button,hint)
                    if bank==1 and (ch==10 or ch==11 and i<8):
                        button.configure(command=lambda:None,takefocus=False)
                        self.dynamic_pads.append((button,ch,i))
                if ch==10 and bank==1:
                    ttk.Label(panel,text='Empty-step cycle (continues across all 64 steps)').grid(row=2,column=0,columnspan=7,sticky='w',pady=8)
                    ttk.Spinbox(panel,from_=1,to=7,textvariable=self.cycle,width=4).grid(row=2,column=7)
                    for i in range(7):self.color_field(panel,f'Cycle {i+1}',self.theme['empty'][i],3+i//4,(i%4)*2,('empty',i))
                    self.color_field(panel,'Velocity 0',self.theme['low'],5,0,('low',None));self.color_field(panel,'Velocity 127',self.theme['high'],5,4,('high',None))
                    ttk.Label(panel,text='The step palette uses the cycle and velocity colors above.').grid(row=6,column=0,columnspan=8,sticky='w',pady=8)
                if ch==11 and bank==1:
                    self.color_field(panel,'Top row color',self.theme['pattern'],3,0,('pattern',None))
                    ttk.Label(panel,text='Top row uses 100% / 65% / 35% brightness. Lower row colors are individual.').grid(row=4,column=0,columnspan=8,sticky='w')
        footer=ttk.Frame(self.win,padding=10);footer.pack(fill='x')
        for label,command in [('Apply',self.apply),('Close',self.close),('Export .settingsjson',self.export),('Import .settingsjson',app.import_settings)]:ttk.Button(footer,text=label,command=command).pack(side='left',padx=5)
        self.cycle.trace_add('write',lambda *args:self.preview_palette())
        for v in self.theme_vars.values():v.trace_add('write',lambda *args:self.preview_palette())
        self.preview_palette()
        self.win.protocol('WM_DELETE_WINDOW',self.close);app.install_key_tag(self.win);tooltips(self.win)
    def preview_palette(self):
        from lighting import blend
        try:
            cycle=self.cycle.get()
            if not 1<=cycle<=7:return
            for button,ch,i in self.dynamic_pads:
                color=self.theme_vars[('empty',i%cycle)].get() if ch==10 else blend('#000000',self.theme_vars[('pattern',None)].get(),(1,.65,.35)[i%3])
                rgb(color);button.config(bg=color)
        except (ValueError,tk.TclError):pass
    def update_row(self):
        try:self.store_row()
        except Exception as exc:messagebox.showerror('Binding',str(exc),parent=self.win)
    def color_field(self,parent,label,color,row,col,key):
        v=tk.StringVar(value=color);self.theme_vars[key]=v
        ttk.Label(parent,text=label).grid(row=row,column=col,sticky='w',pady=6)
        entry=ttk.Entry(parent,textvariable=v,width=10);entry.grid(row=row,column=col+1)
        entry.bind('<Double-Button-1>',lambda e:self.pick_field(v))
    def pick_field(self,v):
        picked=colorchooser.askcolor(v.get(),parent=self.win)[1]
        if picked:v.set(picked)
    def refresh(self):
        for i,row in enumerate(self.rows):
            action,key,src,ch,kind,num=row
            values=(action_label(action),key,pretty_key(key),f'{src}: '+self.names.get(action,self.app.config['controller_names'][src-1]) if src else '—',ch,kind,num)
            if self.tree.exists(str(i)):self.tree.item(str(i),values=values)
            else:self.tree.insert('','end',iid=str(i),values=values)
    def select_row(self,event=None):
        selection=self.tree.selection()
        if not selection:return
        self.current=int(selection[0]);row=self.rows[self.current]
        for v,value in zip(self.fields,[row[1],row[2],row[3],row[4],row[5],self.names.get(row[0],'')]):v.set(str(value))
        self.learn=None;self.learn_text.set('MIDI Learn')
    def store_row(self):
        if self.current is None:return
        key,src,ch,kind,num,name=[v.get() for v in self.fields]
        src,ch,num=int(src),int(ch),int(num)
        if src not in (0,1,2) or not 1<=ch<=16 or not 0<=num<=127 or kind not in ('note_on','control_change'):raise ValueError('Invalid MIDI binding')
        row=self.rows[self.current];row[1:]=[key,src,ch,kind,num];self.names[row[0]]=name
        if src:
            for i,other in enumerate(self.rows):
                if i!=self.current and other[2:]==row[2:]:other[2]=0
        self.refresh()
    def start_learn(self):
        if self.current is not None:self.learn=self.current;self.learn_text.set('Move a control / press a pad…')
    def clear_midi(self):self.fields[1].set('0');self.store_row()
    def receive(self,source,msg):
        if self.learn is None or msg.type not in ('note_on','control_change') or (msg.type=='note_on' and msg.velocity==0):return False
        self.current=self.learn
        for v,value in zip(self.fields[1:],[source,msg.channel+1,msg.type,msg.note if msg.type=='note_on' else msg.control,self.controller_names[source-1].get()]):v.set(str(value))
        self.store_row();self.learn=None;self.learn_text.set('Learned ✓');return True
    def collect(self):
        self.store_row();theme=copy.deepcopy(self.theme);theme['ui']=self.appearance.get();theme['grid_tint']=round(self.tint.get());theme['empty_length']=self.cycle.get()
        for (key,index),v in self.theme_vars.items():
            if index is None:theme[key]=v.get()
            else:theme[key][index]=v.get()
        from lighting import blend
        theme['bank1']['11'][:8]=[blend('#000000',theme['pattern'],(1,.65,.35)[i%3]) for i in range(8)]
        return normalize_settings({'version':4,'ports':[v.get() for v in self.ports],'controller_names':[v.get() for v in self.controller_names],'bindings':self.rows,'binding_names':self.names,'theme':theme})
    def apply(self):
        try:self.app.apply_settings(self.collect())
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.win)
    def export(self):
        try:
            data=self.collect();path=filedialog.asksaveasfilename(parent=self.win,defaultextension='.settingsjson',filetypes=[('MeetStep settings','*.settingsjson')])
            if path:
                from pathlib import Path
                Path(path).write_text(json.dumps(data,indent=2),encoding='utf-8')
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.win)
    def close(self):
        self.learn=None;self.app.settings=None;self.win.destroy();self.app.options_window=None
