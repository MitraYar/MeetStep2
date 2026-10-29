import copy, json, pathlib, queue, sys, time, tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import mido
from collections import deque
from core import Model, Clock, PADS, PADS2, Pickup,ScaleTakeover
from lighting import default_theme, colors, packet, rgb, blend, grid_color
from shortcuts import DEFAULT_BINDINGS, key_id, migrate_bindings,action_label
from editor import Editor
from preferences import SettingsDialog,normalize_settings
from ui_helpers import theme as apply_theme,tooltips,Tooltip
from pitch import defaults as pitch_defaults
from note_input import NoteInput
from gestures import GridGestures
from pitch_controls import PitchControls
from midi_io import MidiPorts,coalesce_controls
ROOT=pathlib.Path(__file__).resolve().parent
CONFIG=pathlib.Path.home()/'.meetstep.json'
DEFAULT={'version':6,'ports':['']*6,'channel_outputs':['']*9,'split_outputs':False,'velocity_mouse_sensitivity':3,'controller_names':['SMK 37 Pro','Controller 2'],'binding_names':{},'bindings':DEFAULT_BINDINGS,'theme':default_theme(),'pitch':pitch_defaults()}
class App:
    def __init__(self,run=True):
        self.root=tk.Tk();self.root.title('MeetStep • SMK 37 Pro')
        self.root.geometry(f'{min(1240,self.root.winfo_screenwidth()-40)}x{min(850,self.root.winfo_screenheight()-70)}');self.root.minsize(1000,650)
        self.held_keys=set();self.key_releases={};self.stroke=None;self.model=Model();self.events=queue.Queue();self.inputs=[];self.outputs=[None]*4
        self.pad_mode=10;self.pad_held=set();self.group=0;self.encoder_attribute=None;self.pickup=Pickup();self.options_window=None
        self.editor=Editor(self.model);self.undo_hold=None;self.audition=False
        self.pitch_controls=PitchControls(self);self.editor.pitch=self.pitch_controls
        self.scaler=ScaleTakeover();self.select_mode=False;self.note_input=NoteInput(self);self.gestures=GridGestures(self);self.fader_raw={}
        self.render_cache=None;self.palette_key=None;self.palette=None
        self.show_gate=False;self.gate_until=0;self.knob_mode='By bank';self.scale_factor={}
        self.length_tens=None
        self.settings=None;self.last_options_tab=0;self.follow_keys=True;self.follow_playhead=False
        self.paint_mode=None;self.drone_mode=False;self.hide_bends=False;self.hide_micro=False
        self.step_holds={};self.forwarded=set();self.tap_times={};self.mute_stroke=None;self.last_midi='';self.last_follow_page=None
        self.held_actions=set();self.last_tap=None;self.forward_map={};self.key_actions={}
        self.config=json.loads(json.dumps(DEFAULT));self.error='';self.led_cache={};self.led_index=0
        try:
            if CONFIG.exists():
                saved=json.loads(CONFIG.read_text())
                self.config=normalize_settings(saved)
        except Exception as exc:self.error=f'Could not load settings: {exc}'
        self.midi_ports=MidiPorts(self.events);self.inputs=self.midi_ports.inputs;self.outputs=self.midi_ports.outputs
        self.pending_midi=deque();self.continuous_cc=set();self.midi_status='';self.closed=False
        apply_theme(self.root,self.config['theme']['ui'])
        icon=ROOT/'assets'/'meetstep.ico'
        if sys.platform=='win32' and icon.exists():self.root.iconbitmap(str(icon))
        self.clock=Clock(self.model,self.send)
        bar=ttk.Frame(self.root,padding=12);bar.pack(fill='x')
        ttk.Label(bar,text='MEETSTEP',font=('Segoe UI',20,'bold')).pack(side='left')
        ttk.Button(bar,text='Play / Stop',command=lambda:self.action('pause')).pack(side='left',padx=10)
        ttk.Button(bar,text='Stop',command=self.clock.stop).pack(side='left')
        ttk.Button(bar,text='Options',command=self.options).pack(side='right')
        ttk.Button(bar,text='Save pattern',command=self.save).pack(side='right')
        ttk.Button(bar,text='Load pattern',command=self.load).pack(side='right')
        self.vars={}
        controls=ttk.Frame(self.root,padding=10);controls.pack(fill='x')
        for name,lo,hi in [('velocity',1,127),('length',15,300),('bpm',30,300),('swing',0,100)]:
            ttk.Label(controls,text={'velocity':'Velocity','length':'Gate %','bpm':'BPM','swing':'Swing'}[name]).pack(side='left');v=tk.DoubleVar(value=getattr(self.model,name));self.vars[name]=v
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
        ttk.Label(nav,text='Length').pack(side='left')
        self.pattern_length=tk.IntVar(value=64)
        length_box=ttk.Combobox(nav,values=list(range(1,65)),textvariable=self.pattern_length,state='readonly',width=3)
        length_box.pack(side='left');length_box.bind('<<ComboboxSelected>>',lambda e:self.set_pattern_length(self.pattern_length.get()))
        ttk.Button(nav,text='← Group',command=lambda:self.move_group(-1)).pack(side='left')
        ttk.Button(nav,text='Group →',command=lambda:self.move_group(1)).pack(side='left')
        editbar=ttk.Frame(self.root,padding=6);editbar.pack(fill='x')
        for label,command in [('Undo · Z',lambda:self.action('undo')),('Redo · X',lambda:self.action('redo')),
                              ('Clear note',lambda:self.clear('note')),('Clear channel',lambda:self.clear('channel')),
                              ('Clear pattern',lambda:self.clear('pattern'))]:
            ttk.Button(editbar,text=label,command=command).pack(side='left',padx=3)
        ttk.Label(editbar,text='Pad layout').pack(side='left',padx=8)
        self.mode_var=tk.IntVar(value=10)
        mode_box=ttk.Combobox(editbar,values=list(range(10,17)),textvariable=self.mode_var,state='readonly',width=3)
        mode_box.pack(side='left');mode_box.bind('<<ComboboxSelected>>',lambda e:self.set_mode(self.mode_var.get()))
        ttk.Button(editbar,text='Reconnect MIDI',command=self.connect).pack(side='left',padx=8)
        toolsbar=ttk.Frame(self.root,padding=5);toolsbar.pack(fill='x')
        self.gate_var=tk.BooleanVar(value=False);self.audition_var=tk.BooleanVar(value=False);self.repeat_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(toolsbar,text='Gate View · G',variable=self.gate_var,command=lambda:self.set_gate(self.gate_var.get())).pack(side='left')
        ttk.Checkbutton(toolsbar,text='Audition · /',variable=self.audition_var,command=lambda:self.set_audition(self.audition_var.get())).pack(side='left')
        ttk.Checkbutton(toolsbar,text='Write ×4 · D',variable=self.repeat_var,command=lambda:setattr(self.editor,'repeat_pages',self.repeat_var.get())).pack(side='left')
        ttk.Button(toolsbar,text='MIDI Panic',command=self.panic).pack(side='left',padx=4)
        self.knob_var=tk.StringVar(value='By bank')
        knobs=ttk.Combobox(toolsbar,textvariable=self.knob_var,values=['By bank','Force velocity','Force gate'],state='readonly',width=14)
        knobs.pack(side='left');knobs.bind('<<ComboboxSelected>>',lambda e:self.pin_knobs())
        ttk.Button(toolsbar,text='Reset knobs',command=self.reset_knobs).pack(side='left')
        ttk.Button(toolsbar,text='Pin faders 1–4',command=self.pin_faders).pack(side='left')
        self.scope_label=ttk.Label(toolsbar,text='');self.scope_label.pack(side='left',padx=8)
        modes=ttk.Frame(self.root,padding=5);modes.pack(fill='x')
        self.mode_buttons={}
        for name,label in [('follow_keys','Keys · Q'),('follow_playhead','Follow · W'),('paint_velocity','Velocity · E'),('paint_gate','Gate · R'),('fill_end','Fill N · F'),('select_mode','Select Mode · Shift S'),('disable_modifiers','Disable modifiers · Ctrl `')]:
            b=ttk.Button(modes,text=label,style='Mode.TButton',command=lambda a=name:self.action(a));b.pack(side='left',padx=2);self.mode_buttons[name]=b
            if name=='fill_end':b._hint=Tooltip(b,'Fill N: Ctrl + 1…0 repeats the next 1…10 source steps from the cursor to the pattern end. Ctrl + D repeats the selected block. A/S chooses note, whole step, or all channels. Left copies and copies to the final N steps stay single.')
        inputsbar=ttk.Frame(self.root,padding=4);inputsbar.pack(fill='x')
        for name,label in [('drone','Drone · V'),('legato','Legato · B'),('nonlegato','Non-legato · N'),('cancel_articulation','Cancel · C'),('mono','Mono · M'),('step_input','Step · Shift K'),('sticky_input','Sticky · Shift L'),('record_input','Record · Shift R'),('hotkey_mode','Hotkey · Ctrl B')]:
            b=ttk.Button(inputsbar,text=label,style='Mode.TButton',command=lambda a=name:self.action(a));b.pack(side='left',padx=2);self.mode_buttons[name]=b
        pitchbar=ttk.Frame(self.root,padding=4);pitchbar.pack(fill='x');ttk.Label(pitchbar,text='Pitch').pack(side='left',padx=8)
        self.pitch_buttons=[]
        for i,label in enumerate(('1 ↘ slow','2 ↘ fast','3 ↗ slow','4 ↗ fast','5 −68¢','6 +22¢','7 −22¢','8 −50¢'),1):
            b=ttk.Button(pitchbar,text=label,style='Mode.TButton',command=lambda i=i:self.action(f'pitch_{i}'));b.pack(side='left',padx=2);self.pitch_buttons.append(b)
        ttk.Button(pitchbar,text='Reset · `',style='Mode.TButton',command=lambda:self.action('pitch_reset')).pack(side='left',padx=4)
        b=ttk.Button(pitchbar,text='Set pitch · Shift `',style='Mode.TButton',command=lambda:self.action('set_pitch'));b.pack(side='left',padx=2);self.mode_buttons['set_pitch']=b
        mute_row=ttk.Frame(self.root);mute_row.pack(fill='x',padx=12,pady=3)
        self.mute_all_button=tk.Label(mute_row,text='MUTES',width=7,relief='raised',cursor='hand2');self.mute_all_button.pack(side='left',padx=(0,22),fill='y')
        self.mute_all_button.bind('<Button-1>',lambda e:self.action('mute_all'));self.mute_all_button.bind('<Button-3>',lambda e:self.action('unmute_all'))
        self.mute_canvas=tk.Canvas(mute_row,height=32,highlightthickness=0);self.mute_canvas.pack(side='left',fill='x',expand=True)
        self.mute_canvas.bind('<Button-1>',lambda e:self.mute_drag(e,True));self.mute_canvas.bind('<Button-3>',lambda e:self.mute_drag(e,False))
        self.mute_canvas.bind('<B1-Motion>',lambda e:self.mute_drag(e,True));self.mute_canvas.bind('<B3-Motion>',lambda e:self.mute_drag(e,False))
        self.mute_canvas.bind('<ButtonRelease-1>',lambda e:self.end_mute());self.mute_canvas.bind('<ButtonRelease-3>',lambda e:self.end_mute())
        self.canvas=tk.Canvas(self.root,bg='#101722',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=12)
        self.canvas.bind('<Button-1>',self.click)
        self.canvas.bind('<Button-3>',lambda e:self.click(e,False))
        self.canvas.bind('<B1-Motion>',lambda e:self.drag(e,1))
        self.canvas.bind('<B3-Motion>',lambda e:self.drag(e,3))
        self.canvas.bind('<Configure>',lambda e:setattr(self,'render_cache',None))
        self.root.bind('<ButtonRelease-1>',lambda e:self.end_stroke(1))
        self.root.bind('<ButtonRelease-3>',lambda e:self.end_stroke(3))
        self.root.bind('<FocusOut>',lambda e:self.focus_out())
        self.status=ttk.Label(self.root,padding=10);self.status.pack(fill='x')
        self.root.bind_class('MeetStepKeys','<KeyPress>',self.key)
        self.root.bind_class('MeetStepKeys','<KeyRelease>',self.key_up)
        self.install_key_tag(self.root)
        tooltips(self.root)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.connect();self.poll()
        if run:self.root.mainloop()
    def cancel_stroke(self):self.model.commit();self.stroke=None
    def install_key_tag(self,widget):
        widget.bindtags(tuple(t for t in widget.bindtags() if t!='MeetStepKeys')[:1]+('MeetStepKeys',)+tuple(t for t in widget.bindtags()[1:] if t!='MeetStepKeys'))
        for child in widget.winfo_children():self.install_key_tag(child)
    def context_change(self):
        self.cancel_stroke();self.pickup.reset();self.scaler.reset();self.editor.reset_selection();self.scale_factor.clear()
        self.note_input.deadline=None
    def select_channel(self,c):
        self.context_change();self.model.channel=c
    def set_pattern_length(self,length):
        if not 1<=length<=64:
            self.error='Pattern length must be 1–64';return
        self.cancel_stroke()
        with self.clock.lock:self.model.set_meta('lengths',(self.model.pattern,),length)
        self.pattern_length.set(length);self.error=''
    def choose_pattern(self,p,preview=None,immediate=False):
        self.context_change();self.model.pattern=p
        if not (self.preview_var.get() if preview is None else preview):self.clock.switch_pattern(p,immediate)
    def set_mode(self,ch):
        if ch!=self.pad_mode:self.pad_held.clear();self.undo_hold=None;self.step_holds.clear()
        self.pad_mode=ch
    def select_group(self,g,attribute=None):
        self.context_change();self.editor.view_offset=0;self.group=max(0,min(7,g));self.model.page=self.group//2
        self.editor.step=self.group*8+self.editor.step%8
        if attribute:self.encoder_attribute=attribute
    def move_group(self,d):self.select_group(self.group+d)
    def pin_knobs(self):self.knob_mode=self.knob_var.get();self.pickup.reset();self.scaler.reset()
    def reset_knobs(self):
        self.knob_var.set('By bank');self.pin_knobs()
    def reset_faders(self):
        self.pickup.reset();self.scaler.reset();self.scale_factor.clear();self.editor.scale_sessions.clear()
    def pin_faders(self):
        self.reset_faders()
        for action,cc in (('velocity',64),('length',65),('swing',66),('tempo',67)):
            for row in self.config['bindings']:
                if row[0]!=action and row[2:]==[1,1,'control_change',cc]:row[2]=0
            rows=[r for r in self.config['bindings'] if r[0]==action]
            if rows:
                for row in rows:row[2:]=[1,1,'control_change',cc]
            else:self.config['bindings'].append([action,'',1,1,'control_change',cc])
        try:CONFIG.write_text(json.dumps(self.config,indent=2));self.error='Faders pinned: 1 velocity · 2 gate · 3 swing · 4 BPM'
        except OSError as exc:self.error=str(exc)
    def set_gate(self,enabled):self.show_gate=enabled;self.gate_var.set(enabled)
    def set_audition(self,enabled):
        self.audition=enabled;self.audition_var.set(enabled)
        if not enabled:self.clock.release_live();self.note_input.routes.clear()
    def panic(self):
        self.clock.stop();self.clock.release_live();self.cancel_stroke()
        self.note_input.routes.clear();self.note_input.deadline=None;self.note_input.collisions.clear()
        self.note_input.held.clear()
        self.pad_held.clear();self.held_actions.clear();self.step_holds.clear();self.undo_hold=None;self.reset_faders();self.clock.pitch.reset();self.clock.manual_wheel=0
        self.release_forwarded()
        while not self.events.empty():
            try:self.events.get_nowait()
            except queue.Empty:break
        for channel in range(16):
            self.send('control_change',channel=channel,control=123,value=0)
            self.send('control_change',channel=channel,control=120,value=0)
    def navigate(self,dx=0,dy=0,extend=False):
        self.cancel_stroke();self.pickup.reset();self.scaler.reset();self.scale_factor.clear()
        self.editor.move(dx,dy,extend);self.group=self.editor.step//8
    def page_move(self,delta):
        self.context_change();self.editor.page(delta);self.group=self.editor.step//8
    def clear(self,scope):
        self.context_change();self.model.clear(scope)
    def end_stroke(self,button):
        self.gestures.release(button)
    def range(self,d):
        self.context_change();old=self.model.base;self.model.base=max(0,min(112,old+d))
        self.model.selected=max(0,min(127,self.model.selected+self.model.base-old))
    def send(self,kind,**kw):
        port=None
        try:
            channel=kw.get('channel')
            port=self.midi_ports.channel_outputs[channel] if hasattr(self,'midi_ports') and channel is not None and channel<9 else self.outputs[0]
            if port:port.send(mido.Message(kind,**kw))
        except Exception as e:
            self.error=f'MIDI output: {e}'
            if hasattr(self,'midi_ports'):self.midi_ports.fail_output(port)
    def connect(self):
        self.clock.stop()
        self.clock.release_live()
        self.note_input.routes.clear();self.note_input.held.clear();self.step_holds.clear();self.undo_hold=None
        self.release_forwarded()
        self.pad_held.clear();self.held_actions.clear();self.reset_faders();self.pending_midi.clear()
        while not self.events.empty():
            try:self.events.get_nowait()
            except queue.Empty:break
        self.led_cache={};self.clock.pitch.configured.clear();self.index_controls()
        self.midi_ports.configure(self.config);self.error=''
    def index_controls(self):
        self.continuous_cc={(src,ch-1,num) for action,key,src,ch,kind,num in self.config['bindings'] if src and kind=='control_change' and (action.startswith('knob_') or action in ('velocity','length','tempo','swing'))}
        self.continuous_cc|={(1,0,i) for i in range(68,72)}
    def midi_health(self):
        self.midi_ports.busy[:]=[any(k[0]==src for k in self.note_input.held) or any(k[0]==src for k in self.pad_held) for src in (1,2)]
        while True:
            try:kind,value=self.midi_ports.notices.get_nowait()
            except queue.Empty:break
            if kind=='status':self.midi_status=value
            elif kind=='input_lost':
                self.note_input.disconnect(value)
                if self.undo_hold and self.undo_hold['key'][0]==value:self.undo_hold=None
                for key in set(self.pad_held)|set(self.forward_map):
                    if key[0]==value:
                        self.step_holds.pop(key,None);self.pad_held.discard(key);self.release_control(key)
                self.held_actions.difference_update(r[0] for r in self.config['bindings'] if r[2]==value)
            elif kind=='output_ready':
                self.led_cache.clear()
                channels={c for c,n in enumerate(self.midi_ports.route_names) if n==value}
                if channels:self.clock.recover_output(channels,value==self.config['ports'][2])
    def action(self,name,value=127,extend=False):
        if name=='play':self.clock.toggle()
        elif name=='pause':self.clock.toggle()
        elif name=='stop':self.clock.stop()
        elif name=='options':self.options()
        elif name in ('undo','redo'):
            self.cancel_stroke();self.pickup.reset();self.scaler.reset();self.model.history(name=='redo');self.group=self.editor.step//8
            self.clock.reconcile_mutes()
        elif name in ('left','right'):self.move_group(-1 if name=='left' else 1)
        elif name in ('group_left','group_right'):self.move_group(-1 if name=='group_left' else 1)
        elif name in ('prev_page','next_page','page_left','page_right'):self.page_move(-1 if name in ('prev_page','page_left') else 1)
        elif name in ('view_left','view_right'):
            self.cancel_stroke();self.editor.shift_view(-1 if name=='view_left' else 1)
        elif name in ('up_page','down_page'):self.range(16 if name=='up_page' else -16)
        elif name.startswith('grid_'):
            self.note_input.deadline=None
            dx,dy={'grid_left':(-1,0),'grid_right':(1,0),'grid_up':(0,1),'grid_down':(0,-1)}[name]
            self.navigate(dx,dy,extend)
            if dx and not extend:self.note_input.moved()
        elif name=='audition':self.set_audition(not self.audition)
        elif name=='gate_view':self.set_gate(not self.show_gate)
        elif name=='repeat_pages':self.editor.repeat_pages=not self.editor.repeat_pages;self.repeat_var.set(self.editor.repeat_pages)
        elif name in ('scope_note','scope_channel'):
            self.cancel_stroke();self.reset_faders()
            if name=='scope_note':self.editor.toggle_note_scope()
            else:self.editor.toggle_channel_scope()
        elif name in ('home','end'):
            self.context_change();self.editor.view_offset=0;self.editor.step=0 if name=='home' else self.model.lengths[self.model.pattern]-1
            self.model.page=self.editor.step//16;self.group=self.editor.step//8
        elif name in ('offset_up','offset_down'):
            self.cancel_stroke();self.model.base+=1 if name=='offset_up' else -1
        elif name in ('follow_keys','follow_playhead','drone'):
            attr={'drone':'drone_mode'}.get(name,name);setattr(self,attr,not getattr(self,attr))
        elif name in ('paint_velocity','paint_gate'):
            mode='velocity' if name=='paint_velocity' else 'length';self.paint_mode=None if self.paint_mode==mode else mode
        elif name=='fill_end':self.editor.fill_to_end=not self.editor.fill_to_end
        elif name=='select_mode':self.cancel_stroke();self.select_mode=not self.select_mode
        elif name=='set_pitch':self.cancel_stroke();self.pitch_controls.mode=not self.pitch_controls.mode
        elif name=='disable_modifiers':
            self.cancel_stroke();self.follow_keys=False;self.follow_playhead=False;self.paint_mode=None;self.select_mode=False
            self.editor.fill_to_end=False;self.editor.articulation=None;self.drone_mode=False;self.pitch_controls.mode=False
            self.pitch_controls.held.clear();self.pitch_controls.used.clear();self.pitch_controls.reset_held=False
            self.pitch_controls.reset();self.editor.reset_selection();self.reset_faders()
            self.note_input.step=False;self.note_input.sticky=False;self.note_input.record=False;self.note_input.deadline=None
            self.model.set_meta('mono',(self.model.channel,),False)
        elif name in ('step_input','sticky_input','record_input','hotkey_mode'):
            field={'step_input':'step','sticky_input':'sticky','record_input':'record','hotkey_mode':'hotkeys'}[name]
            setattr(self.note_input,field,not getattr(self.note_input,field));self.note_input.deadline=None
            if name=='sticky_input' and self.note_input.sticky:self.note_input.step=True
        elif name=='mono':self.cancel_stroke();self.model.toggle_mono();self.reset_faders()
        elif name in ('delete_selection','delete_selection_back','insert_selection'):
            self.cancel_stroke();m=self.model;m.begin();cells=self.editor.selection.copy()
            if not cells and name!='insert_selection':cells={(m.selected,self.editor.step)}
            for n,s in sorted(cells):
                c=m.channel
                if name=='insert_selection':
                    if m.patterns[m.pattern][c][n][s] is None:m.write_cell(m.pattern,c,n,s,self.note_input.cell(c,m.velocity))
                else:m.set_cell(m.pattern,c,n,s,None)
            if name!='insert_selection':
                for n in {n for n,s in cells}:
                    if all((n,s) in cells for s in range(64)):m.set_meta('drones',(m.pattern,m.channel,n),False)
            m.commit()
        elif name=='duplicate_selection' or name.startswith(('duplicate_','duplicate_end_','duplicate_left_')):
            count=None if name=='duplicate_selection' else int(name.split('_')[-1])
            self.cancel_stroke();self.reset_faders();self.editor.duplicate(count,name.startswith('duplicate_end_'),name.startswith('duplicate_left_'));self.group=self.editor.step//8
        elif name in ('legato','nonlegato','cancel_articulation'):
            m=self.model;m.begin()
            target='gate' if name=='cancel_articulation' else name
            if self.editor.articulation==target:target=None
            self.editor.articulation=target
            if target is not None:
                for n,s in self.editor.selection:m.set_articulation(n,s,target)
            m.commit()
        elif name.startswith('pitch_'):
            if name=='pitch_reset':self.pitch_controls.reset()
            else:self.pitch_controls.toggle(int(name.split('_')[1]))
        elif name in ('hide_bends','hide_micro'):setattr(self,name,not getattr(self,name))
        elif name in ('mute_all','unmute_all'):
            self.model.begin()
            for c in range(9):self.clock.mute(c,name=='mute_all')
            self.model.commit()
        elif name.startswith('mute_'):
            c=int(name.split('_')[-1]);self.clock.mute(c,not self.model.muted[c])
        elif name.startswith('delete_channel_'):
            double=self.double_tap(name);previous=self.model.channel
            if not double:self.model.channel=int(name.split('_')[-1])
            self.clear('pattern' if double else 'channel');self.model.channel=previous
        elif name.startswith('pattern_'):self.choose_pattern(int(name.split('_')[-1]),False,self.double_tap(name))
        elif name.startswith(('copy_pattern_','copy_note_')):
            note_only=name.startswith('copy_note_');whole=not note_only and self.double_tap(name)
            self.model.copy_to(int(name.split('_')[-1]),note_only,whole)
        elif name.startswith('channel_hotkey_'):self.select_channel(int(name.split('_')[-1]))
        elif name.startswith('length_tens_'):
            i=int(name.split('_')[-1]);self.length_tens=0 if i==7 else i*10
        elif name.startswith('pad_layout_'):self.set_mode(int(name.split('_')[-1]))
        elif name.startswith('pad_'):
            _,ch,i=name.split('_');self.held_actions.add(name);self.handle_pad(int(ch),int(i),True,('shortcut',name))
        elif name.startswith('select_channel_'):self.select_channel(int(name.split('_')[-1]))
        elif name.startswith('knob_'):
            _,attribute,index=name.split('_');self.knob('length' if attribute=='gate' else 'velocity',int(index),value,name)
        elif name.startswith('clear_'):self.clear(name[6:])
        elif name in ('save','load','panic','reset_knobs','pin_faders','import_settings'):getattr(self,name)()
        elif name=='view_only':self.preview_var.set(not self.preview_var.get())
        elif name.startswith('force_'):
            self.knob_var.set('Force velocity' if name=='force_velocity' else 'Force gate');self.pin_knobs()
        elif name in ('export_settings','settings_apply','settings_close'):
            if not self.settings:self.options()
            getattr(self.settings,{'export_settings':'export','settings_apply':'apply','settings_close':'close'}[name])()
        elif name=='set_length':self.set_pattern_length(max(1,min(64,round(1+value*63/127))))
        else:
            attr,lo,hi={'velocity':('velocity',1,127),'length':('length',15,300),'tempo':('bpm',30,300),'swing':('swing',0,100)}[name]
            val=self.scaler.value(('global',attr),value,getattr(self.model,attr),lo,hi)
            if val is not None:setattr(self.model,attr,val);self.vars[attr].set(val)
    def double_tap(self,name):
        now=time.monotonic();double=bool(self.last_tap and self.last_tap[0]==name and now-self.last_tap[1]<.4)
        self.last_tap=None if double else (name,now);return double
    def mute_drag(self,event,value):
        if not 0<=event.x<self.mute_canvas.winfo_width():return
        if self.mute_stroke is None:self.model.begin();self.mute_stroke={'visited':set(),'last':None}
        c=min(8,int(event.x/(self.mute_canvas.winfo_width()/9)))
        previous=c if self.mute_stroke['last'] is None else self.mute_stroke['last']
        for channel in range(min(previous,c),max(previous,c)+1):
            if channel not in self.mute_stroke['visited']:self.clock.mute(channel,value);self.mute_stroke['visited'].add(channel)
        self.mute_stroke['last']=c
    def end_mute(self):self.model.commit();self.mute_stroke=None
    def release_forwarded(self):
        if len(self.outputs)>3 and self.outputs[3]:
            for c,n in self.forwarded:
                try:self.outputs[3].send(mido.Message('note_off',channel=c,note=n,velocity=0))
                except Exception as exc:self.error=str(exc)
        self.forwarded.clear()
        self.forward_map.clear()
    def key(self,e):
        key=key_id(e)
        if e.widget.winfo_class() in ('Entry','TEntry','Text','TSpinbox','Spinbox','TCombobox') and key!='CTRL+VK_BF' and not key.startswith('ALT+'):return
        code=int(key[-2:],16)
        if self.length_tens is not None and key.startswith('ALT+') and 0x30<=code<=0x39:
            self.set_pattern_length(self.length_tens+code-0x30);self.length_tens=None;return 'break'
        action=next((r[0] for r in self.config['bindings'] if r[1] and r[1]==key),None)
        if not action and key.startswith('SHIFT+'):
            action=next((r[0] for r in self.config['bindings'] if r[1]==key[6:] and r[0].startswith('grid_')),None)
        if not action:return
        if e.keycode in self.key_releases:self.root.after_cancel(self.key_releases.pop(e.keycode))
        repeat=action.startswith('grid_') or action in ('left','right','group_left','group_right','up_page','down_page','offset_up','offset_down','view_left','view_right','page_left','page_right')
        if e.keycode in self.held_keys and not repeat:return 'break'
        self.held_keys.add(e.keycode);self.key_actions[e.keycode]=action
        self.action(action,extend=bool(e.state&1))
        if action=='pitch_reset':self.pitch_controls.reset_held=True
        elif action.startswith('pitch_'):self.pitch_controls.held.add(int(action.split('_')[1]))
        return 'break'
    def key_up(self,e):
        if key_id(e).endswith('VK_12'):self.length_tens=None
        def release():
            self.held_keys.discard(e.keycode);self.key_releases.pop(e.keycode,None)
            action=self.key_actions.pop(e.keycode,None)
            if action and action.startswith('pad_'):self.release_control(('shortcut',action));self.held_actions.discard(action)
            if action=='pitch_reset':self.pitch_controls.reset_held=False
            elif action and action.startswith('pitch_'):self.pitch_controls.release(int(action.split('_')[1]))
        if e.keycode in self.key_releases:self.root.after_cancel(self.key_releases.pop(e.keycode))
        self.key_releases[e.keycode]=self.root.after_idle(release)
    def focus_out(self):
        self.root.after_idle(self.check_focus)
    def check_focus(self):
        focused=self.root.focus_get()
        if focused is not None and focused.winfo_toplevel()==self.root:return
        self.cancel_stroke();self.held_keys.clear()
        self.end_mute()
        for action in self.key_actions.values():
            if action.startswith('pad_'):self.release_control(('shortcut',action));self.held_actions.discard(action)
        self.key_actions.clear()
        for number in list(self.pitch_controls.held):self.pitch_controls.release(number)
        self.pitch_controls.reset_held=False
        self.length_tens=None
        for callback in self.key_releases.values():self.root.after_cancel(callback)
        self.key_releases.clear()
    def midi(self,source,msg,at=None):
        at=time.perf_counter() if at is None else at
        if hasattr(msg,'channel'):
            self.last_midi=f'IN {source} · Ch {msg.channel+1} · {msg.type} '+(f'CC{msg.control}={msg.value}' if msg.type=='control_change' else '')
        if self.settings and self.settings.receive(source,msg):return
        if msg.type=='pitchwheel':
            if source==1 and msg.channel==0 and self.audition:self.clock.input_pitch(msg.pitch)
            return
        event_key=(source,getattr(msg,'channel',0),getattr(msg,'note',-1))
        if msg.type in ('note_off','note_on') and (msg.type=='note_off' or msg.velocity==0):
            if source==1 and msg.channel<9:self.note_input.release(source,msg.channel,msg.note)
            self.release_control(event_key)
            self.pad_held.discard(event_key)
            for row in self.config['bindings']:
                if row[2:]==[source,msg.channel+1,'note_on',msg.note]:self.held_actions.discard(row[0])
            return
        if msg.type not in ('note_on','control_change'):return
        if msg.type=='note_on':
            if source==1 and 10<=msg.channel+1<=16:self.set_mode(msg.channel+1)
            if not (source==1 and msg.channel<9):
                if event_key in self.pad_held:return
                self.pad_held.add(event_key)
        number=msg.note if msg.type=='note_on' else msg.control
        row=next((r for r in self.config['bindings'] if r[2:]==[source,msg.channel+1,msg.type,number]),None)
        if row:
            action=row[0];value=msg.velocity if msg.type=='note_on' else msg.value
            if action.startswith('pad_'):
                if action.startswith('pad_layout_'):self.action(action,value);return
                if msg.type=='control_change':
                    event_key=(source,msg.channel,'cc',msg.control)
                    if value==0:self.release_control(event_key);self.held_actions.discard(action);self.pad_held.discard(event_key);return
                    if event_key in self.pad_held:return
                    self.pad_held.add(event_key)
                _,ch,i=action.split('_');self.held_actions.add(action)
                self.handle_pad(int(ch),int(i),True,event_key,value)
            elif action in ('velocity','length','tempo','swing'):self.fader('bpm' if action=='tempo' else action,value)
            elif msg.type!='control_change' or action.startswith('knob_') or value>0:self.action(action,value)
            return
        if source==1 and msg.type=='control_change' and msg.channel==0 and msg.control in (68,69,70,71):
            self.fader({68:'velocity',69:'length',70:'swing',71:'bpm'}[msg.control],msg.value);return
        if source==1 and msg.type=='note_on' and msg.channel<9:
            self.note_input.press(source,msg.channel,msg.note,msg.velocity,at)
    def handle_pad(self,ch,i,pressed,event_key,value=100):
        if ch>=14:
            if self.outputs[3]:
                note=(PADS+PADS2)[i];self.outputs[3].send(mido.Message('note_on',channel=ch-1,note=note,velocity=value));self.forwarded.add((ch-1,note));self.forward_map[event_key]=(ch-1,note)
            return
        if ch==13:return
        if ch==10 and i<16:
            step=self.model.page*16+i;note=self.model.selected
            self.step_holds[event_key]={'start':time.monotonic(),'step':step,'note':note,'pattern':self.model.pattern,'channel':self.model.channel,'selected':False}
            return
        if ch==12 and i<9:self.action(f'mute_{i}');return
        if ch==11 and i<8:
            held=self.held_actions
            if 'pad_11_11' in held or 'pad_11_12' in held:
                old=self.model.pattern;self.model.pattern=i
                self.model.clear('note' if 'pad_11_12' in held else 'pattern');self.model.pattern=old
            elif 'pad_11_10' in held:self.context_change();self.model.copy_to(i,True)
            elif 'pad_11_9' in held:self.context_change();self.model.copy_to(i)
            else:self.choose_pattern(i,'pad_11_8' in held)
            return
        if (ch==11 and i==15) or (i==31 and ch!=10):
            self.undo_hold={'key':event_key,'start':time.monotonic(),'fired':False}
        elif i==31 and ch==10:self.action('undo')
        elif i==24:self.action('pause')
        elif ch==10 and i==23:self.action('redo')
        elif ch==10 and i in (29,30):self.move_group(-1 if i==29 else 1)
    def release_control(self,event_key):
        self.release_step(event_key)
        if self.undo_hold and self.undo_hold['key']==event_key:
            if not self.undo_hold['fired']:self.action('redo' if time.monotonic()-self.undo_hold['start']>=1 else 'undo')
            self.undo_hold=None
        forwarded=self.forward_map.pop(event_key,None)
        if forwarded:
            if self.outputs[3] and forwarded not in self.forward_map.values():
                self.outputs[3].send(mido.Message('note_off',channel=forwarded[0],note=forwarded[1],velocity=0))
                self.forwarded.discard(forwarded)
    def select_held_step(self,hold):
        m=self.model;e=self.editor
        if m.mono[m.channel]:hold['note']=m.step_note(hold['step'])
        cell=(hold['note'],hold['step'])
        if cell in e.selection:e.selection.remove(cell)
        else:e.selection.add(cell)
        if e.articulation is not None:m.set_articulation(*cell,e.articulation)
        if e.selection:
            e.step=min(s for n,s in e.selection)
            if not m.mono[m.channel]:m.select(max(n for n,s in e.selection))
        self.group=e.step//8;hold['selected']=True;self.reset_faders()
    def release_step(self,event_key):
        hold=self.step_holds.pop(event_key,None)
        if not hold or (hold['pattern'],hold['channel'])!=(self.model.pattern,self.model.channel):return
        if hold['selected']:return
        if time.monotonic()-hold['start']>=.5:self.select_held_step(hold);return
        self.cancel_stroke();self.model.begin()
        n=hold['note'];s=hold['step'];self.editor.step=s;self.model.select(n)
        m=self.model;old=m.step_note(s)
        if m.mono[m.channel] and old!=n and m.notes[old][s] and not self.pitch_controls.mode and not self.pitch_controls.reset_held:
            m.write_cell(m.pattern,m.channel,n,s,m.notes[old][s])
            if self.pitch_controls.held:self.pitch_controls.paint(n,s)
        else:self.editor.edit(n,s,m.notes[n][s] is None or self.pitch_controls.mode or self.pitch_controls.reset_held)
        self.model.commit();self.group=s//8
    def knob(self,attribute,index,raw,name):
        if self.knob_mode!='By bank':attribute='velocity' if self.knob_mode=='Force velocity' else 'length'
        self.encoder_attribute=attribute;s=self.group*8+index;n=self.model.step_note(s) if self.model.mono[self.model.channel] else self.model.selected;cell=self.model.notes[n][s]
        if cell is None:self.error=f'{attribute.title()} knob {index+1}: step {s+1} is empty';return
        i=0 if attribute=='velocity' else 1;lo,hi=(1,127) if i==0 else (15,300)
        value=self.scaler.value((name,self.model.pattern,self.model.channel,n,s),raw,cell[i],lo,hi)
        if value is None:self.error=f'{attribute.title()} step {s+1}: Scale anchored; turn to edit';return
        updated=list(cell);updated[i]=value;self.editor.scale_sessions.clear();self.scale_factor.clear()
        self.model.set_cell(self.model.pattern,self.model.channel,n,s,updated);self.error=''
        if i:self.gate_until=time.monotonic()+1
    def fader(self,attribute,raw):
        if attribute in ('bpm','swing'):self.action('tempo' if attribute=='bpm' else 'swing',raw);return
        if self.fader_raw.get(attribute)==raw:return
        self.fader_raw[attribute]=raw
        i=0 if attribute=='velocity' else 1;lo,hi=(1,127) if i==0 else (15,300)
        m=self.model;n=m.step_note(self.editor.step) if m.mono[m.channel] else m.selected
        cell=m.notes[n][self.editor.step]
        absolute=self.stroke is not None and self.stroke.get('button')==1
        if absolute:
            value=round(lo+(hi-lo)*raw/127);setattr(m,attribute,value);self.vars[attribute].set(value)
            if self.stroke.get('kind') in ('paint','draw'):self.stroke['absolute']=True
            targets=self.editor.selected_targets() if self.editor.selection else {(m.channel,n,self.editor.step)}
            if m.transaction is None:m.begin()
            for c,n,s in targets:
                cell=m.patterns[m.pattern][c][n][s]
                if cell:
                    updated=list(cell);updated[i]=value;m.set_cell(m.pattern,c,n,s,updated)
        elif self.editor.selection:
            key=('scale',attribute,frozenset(self.editor.selection),m.pattern,m.channel)
            current=self.scale_factor.get(attribute,64)
            value=self.scaler.value(key,raw,current,0,127)
            if value is not None:
                self.scale_factor[attribute]=value
                self.editor.scale(attribute,value/64 if value<=64 else 1+(value-64)/63)
        else:
            target=cell[i] if cell else getattr(m,attribute)
            key=('fader',attribute,m.pattern,m.channel,n,self.editor.step)
            value=self.scaler.value(key,raw,target,lo,hi)
            if value is not None:
                setattr(m,attribute,value);self.vars[attribute].set(value)
                if cell:
                    updated=list(cell);updated[i]=value
                    m.set_cell(m.pattern,m.channel,n,self.editor.step,updated)
        if attribute=='length':self.gate_until=time.monotonic()+1
    def click(self,e,on=True):self.gestures.press(e,on)
    def drag(self,e,button):self.gestures.move(e,button)
    def render_signature(self):
        m=self.model;e=self.editor;ni=self.note_input
        preset=m.pitch_presets[m.channel]
        return (m.revision,m.pattern,m.playing,m.channel,m.base,m.page,m.selected,m.velocity,m.length,m.bpm,m.swing,
                e.step,frozenset(e.selection),e.scope,e.articulation,e.repeat_pages,e.fill_to_end,e.view_offset,self.pitch_controls.mode,self.group,self.encoder_attribute,
                self.clock.step,self.clock.queued,self.clock.running,self.select_mode,self.follow_keys,self.follow_playhead,
                self.paint_mode,self.drone_mode,ni.step,ni.sticky,ni.record,ni.hotkeys,self.hide_micro,self.hide_bends,
                preset.get('micro'),preset.get('bend'),self.show_gate,time.monotonic()<self.gate_until,
                self.length_tens,self.error,self.last_midi)
    def poll(self):
        try:self.poll_once()
        except Exception as exc:
            self.error=f'UI recovered: {type(exc).__name__}: {exc}'
            try:
                import traceback
                log=CONFIG.with_suffix('.log')
                if log.exists() and log.stat().st_size>262144:log.write_text('',encoding='utf-8')
                with log.open('a',encoding='utf-8') as f:traceback.print_exc(file=f)
            except OSError:pass
        finally:
            if not self.closed:self.poll_id=self.root.after(20,self.poll)
    def poll_once(self):
        self.midi_health();batch=[]
        for _ in range(2048):
            try:event=self.events.get_nowait()
            except queue.Empty:break
            batch.append(event)
        self.pending_midi.extend(coalesce_controls(batch,self.continuous_cc))
        deadline=time.perf_counter()+.008
        while self.pending_midi and time.perf_counter()<deadline:
            event=self.pending_midi.popleft()
            if len(event)>3 and event[3]!=self.midi_ports.generations[event[0]-1]:continue
            try:self.midi(*event[:3])
            except Exception as exc:self.error=f'MIDI: {exc}'
        self.note_input.poll();self.gestures.poll()
        for hold in self.step_holds.values():
            if not hold['selected'] and time.monotonic()-hold['start']>=.5:
                if (hold['pattern'],hold['channel'])==(self.model.pattern,self.model.channel):self.select_held_step(hold)
                else:hold['selected']=True
        if self.undo_hold and not self.undo_hold['fired'] and time.monotonic()-self.undo_hold['start']>=1:
            self.action('redo');self.undo_hold['fired']=True
        if self.follow_playhead and self.clock.running and self.clock.step>=0:
            page=self.clock.step//16
            if page!=self.model.page:self.cancel_stroke();self.pickup.reset();self.model.page=page;self.group=self.clock.step//8
        signature=self.render_signature()
        if signature!=self.render_cache:self.draw();self.render_cache=signature
        self.led()
    def led(self):
        if not self.outputs[2]:return
        m=self.model;key=(m.revision,m.pattern,m.channel,m.selected,m.page,self.pad_mode,id(self.config['theme']))
        if key!=self.palette_key:self.palette=colors(m,self.config['theme'],self.pad_mode);self.palette_key=key
        palette=self.palette
        for _ in range(32):
            i=self.led_index;self.led_index=(i+1)%32
            color=palette[i]
            if self.led_cache.get(i)!=color:
                try:self.outputs[2].send(mido.Message.from_bytes(packet(i,color)));self.led_cache[i]=color
                except Exception as e:self.error=str(e);self.midi_ports.fail_output(self.outputs[2])
                break
    def draw(self):
        c=self.canvas;c.delete('all');w=c.winfo_width();h=c.winfo_height();cw=(w-80)/16;rh=(h-30)/16
        light=self.config['theme']['ui']=='Light';c.configure(bg='#edf1f6' if light else '#101722')
        self.mute_canvas.configure(bg='#edf1f6' if light else '#101722')
        offset=self.editor.view_start;theme=self.config['theme']
        for s in range(16):c.create_text(80+(s+.5)*cw,15,text=str(offset+s+1),fill='#68e0ce' if offset+s==self.clock.step else '#94a3b8')
        for r in range(16):
            n=self.model.base+15-r;y=30+r*rh
            label=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][n%12]+str(n//12-2)
            marker=' ∞' if self.model.drones[self.model.pattern][self.model.channel][n] else ''
            c.create_text(38,y+rh/2,text=f'{label} · {n}'+marker,fill=('#136955' if light else '#68e0ce') if n==self.model.selected else '#536478' if light else '#94a3b8')
            for s in range(16):
                cell=self.model.notes[n][offset+s];x=80+s*cw
                color=grid_color(theme,offset+s,cell)
                if offset+s>=self.model.lengths[self.model.pattern]:color=blend('#101722',color,.25)
                selected=(n,offset+s) in self.editor.selection
                cursor=n==self.model.selected and offset+s==self.editor.step
                outline='#da9200' if selected and light else '#ffcf6a' if selected else ('#19666e' if light else '#ffffff') if cursor else '#3a9d8f' if offset+s==self.clock.step and self.model.pattern==self.model.playing else ('#b4c8da' if light else '#34476a') if (offset+s)//8==self.group else ('#d2dce6' if light else '#28364a')
                short=cell and cell[1]<100
                c.create_rectangle(x+2,y+2,x+cw-2,y+rh-2,fill=grid_color(theme,offset+s,None) if short else color,outline=outline,width=2 if selected or cursor else 1)
                if short:
                    width=cw-6;gate=cell[1]/100
                    c.create_polygon(x+3,y+3,x+3+width*gate,y+3,x+3+width*min(1,gate+.06),y+rh-3,x+3,y+rh-3,fill=color,outline='',tags=('gate_shape',f'gate:{n}:{offset+s}'))
                if cell:
                    value=f'{cell[1]}%' if self.show_gate or time.monotonic()<self.gate_until else str(cell[0])
                    text_color=('#102025' if light else '#ffffff') if short else '#ffffff' if sum(rgb(color))<380 else '#102025'
                    c.create_text(x+cw/2,y+rh/2,text=value,fill=text_color)
                    if len(cell)>2:
                        meta=cell[2];annotation=''
                        if meta.get('bend') and not self.hide_bends:annotation+='↘' if meta.get('approach',{}).get('start',30 if meta['bend'] in (1,2) else -30)>=0 else '↗'
                        if meta.get('micro') and not self.hide_micro:annotation+=f"{meta['micro']:+}"
                        if annotation:c.create_text(x+cw-4,y+3,text=annotation,anchor='ne',font=('Segoe UI',7),fill='#ffffff')
                        if meta.get('mode') in ('legato','nonlegato'):c.create_text(x+4,y+rh-3,text='L' if meta['mode']=='legato' else 'N',anchor='sw',font=('Segoe UI',7),fill='#102025')
        self.channel_var.set(self.model.channel+1);self.mode_var.set(self.pad_mode)
        self.pattern_length.set(self.model.lengths[self.model.pattern])
        for i,b in enumerate(self.pattern_buttons):b.config(text=f'{i+1}'+('▶' if i==self.model.playing else '')+('…' if i==self.clock.queued else '')+('•' if i==self.model.pattern else ''))
        self.mute_canvas.delete('all');width=self.mute_canvas.winfo_width()/9
        for i,muted in enumerate(self.model.muted):
            self.mute_canvas.create_rectangle(i*width+2,2,(i+1)*width-2,30,fill='#bc4259' if muted else '#23394b',outline='')
            self.mute_canvas.create_text((i+.5)*width,16,text=f'{i+1}  '+('MUTED' if muted else 'ON'),fill='white')
        states={'follow_keys':self.follow_keys,'follow_playhead':self.follow_playhead,'paint_velocity':self.paint_mode=='velocity','paint_gate':self.paint_mode=='length','fill_end':self.editor.fill_to_end,'drone':self.drone_mode,'legato':self.editor.articulation=='legato','nonlegato':self.editor.articulation=='nonlegato','cancel_articulation':self.editor.articulation=='gate','select_mode':self.select_mode,'mono':self.model.mono[self.model.channel],'step_input':self.note_input.step,'sticky_input':self.note_input.sticky,'record_input':self.note_input.record,'hotkey_mode':self.note_input.hotkeys}
        states.update(set_pitch=self.pitch_controls.mode,disable_modifiers=False)
        for name,button in self.mode_buttons.items():button.state(['pressed'] if states[name] else ['!pressed'])
        preset=self.model.pitch_presets[self.model.channel]
        for i,button in enumerate(self.pitch_buttons,1):
            button.state(['pressed'] if (preset.get('bend')==i if i<5 else preset.get('micro_key')==i) else ['!pressed'])
            if i>=5:button.configure(text=f"{i} {self.config['pitch']['micro'][i-5]['cents']:+g}¢")
            else:
                value=self.config['pitch']['approach'][i-1];button.configure(text=f"{i} {'↘' if value['start']>=0 else '↗'} {value['time']}")
        for name,var in self.vars.items():var.set(getattr(self.model,name))
        self.scope_label.config(text={'note':'A: note','step':'A: whole step','all_channels':'S: all channels'}[self.editor.scope]+f' · {len(self.editor.selection)} selected')
        pending=f'Length: {self.length_tens//10}_ (Alt + digit)' if self.length_tens is not None else self.error or self.last_midi or self.midi_status
        self.status.config(text=f'View P{self.model.pattern+1} / Play P{self.model.playing+1} · Ch {self.model.channel+1} · Note {self.model.selected} · Steps {offset+1}–{offset+16} · Group {self.group+1} {self.encoder_attribute or "knobs by bank"} | {self.model.bpm} BPM | '+pending)
    def options(self):
        self.cancel_stroke()
        if self.options_window and self.options_window.winfo_exists():
            self.options_window.lift();return
        self.settings=SettingsDialog(self)
    def mido_inputs(self):return mido.get_input_names()
    def mido_outputs(self):return mido.get_output_names()
    def apply_settings(self,data):
        updated=normalize_settings(data)
        CONFIG.write_text(json.dumps(updated,indent=2),encoding='utf-8')
        changed=any(updated.get(k)!=self.config.get(k) for k in ('ports','split_outputs','channel_outputs'));self.config=updated;self.index_controls()
        self.pickup.reset();self.scaler.reset();self.led_cache={};self.render_cache=None;self.palette_key=None;apply_theme(self.root,self.config['theme']['ui'])
        if changed:self.connect()
    def import_settings(self):
        path=filedialog.askopenfilename(filetypes=[('MeetStep settings','*.settingsjson'),('JSON','*.json')])
        if not path:return
        try:
            self.apply_settings(json.loads(pathlib.Path(path).read_text(encoding='utf-8')))
            if self.settings:self.settings.close()
            self.options()
        except Exception as exc:messagebox.showerror('Settings',str(exc))
    def save(self):
        p=filedialog.asksaveasfilename(defaultextension='.patternsjson',filetypes=[('MeetStep project','*.patternsjson')])
        if p:pathlib.Path(p).write_text(json.dumps(self.model.dump()))
    def load(self):
        self.cancel_stroke()
        p=filedialog.askopenfilename(filetypes=[('MeetStep project','*.patternsjson'),('Legacy project','*.json')])
        if not p:return
        try:
            data=json.loads(pathlib.Path(p).read_text())
            self.clock.stop();self.model.load(data);self.context_change();self.vars['bpm'].set(self.model.bpm)
        except Exception as e:messagebox.showerror('Pattern','Invalid pattern: '+str(e))
    def close(self):
        self.closed=True
        self.root.after_cancel(self.poll_id)
        self.release_forwarded()
        self.clock.close()
        self.midi_ports.close()
        self.root.destroy()
if __name__=='__main__':App()
