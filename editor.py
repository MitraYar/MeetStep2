"""Grid navigation and editing transactions, independent of Tk and MIDI."""
class Editor:
    def __init__(self,model):
        self.model=model;self.step=0;self.selection=set();self.anchor=None
        self.scope='note';self.repeat_pages=False;self.scale_sessions={};self.fill_to_end=False;self.extent=None
        model.capture_context=self.snapshot;model.restore_context=self.restore
    def snapshot(self):
        m=self.model
        return {'pattern':m.pattern,'channel':m.channel,'selected':m.selected,'base':m.base,'page':m.page,'step':self.step,'selection':list(self.selection),'anchor':self.anchor,'extent':self.extent,'scope':self.scope}
    def restore(self,context):
        m=self.model
        for name in ('pattern','channel','selected','base','page'):setattr(m,name,context[name])
        self.step=context.get('step',0);self.selection=set(map(tuple,context.get('selection',[])))
        self.anchor=context.get('anchor');self.extent=context.get('extent');self.scope=context.get('scope','note');self.scale_sessions.clear()
    def reset_selection(self):
        self.selection.clear();self.anchor=None;self.extent=None;self.scale_sessions.clear()
    def rectangle(self,start,end):
        n0,s0=start;n1,s1=end
        self.selection={(n,s) for n in range(min(n0,n1),max(n0,n1)+1) for s in range(min(s0,s1),max(s0,s1)+1)}
        self.extent=end;self.step=min(s0,s1);self.model.select(max(n0,n1))
        self.scale_sessions.clear()
    def move(self,dx=0,dy=0,extend=False):
        start=self.extent if extend and self.extent else (self.model.selected,self.step)
        if extend:
            if self.anchor is None:self.anchor=start
        else:self.reset_selection()
        self.step=max(0,min(63,start[1]+dx))
        self.model.select(max(0,min(127,start[0]+dy)))
        self.model.page=self.step//16
        if extend:self.rectangle(self.anchor,(self.model.selected,self.step))
    def page(self,delta):
        self.reset_selection();self.model.page=(self.model.page+delta)%4
        self.step=self.model.page*16+self.step%16
    def toggle_note_scope(self):
        self.scope='step' if self.scope=='note' else 'note';self.scale_sessions.clear()
    def toggle_channel_scope(self):
        self.scope='step' if self.scope=='all_channels' else 'all_channels';self.scale_sessions.clear()
    def targets(self,cells=None):
        cells=self.selection if cells is None else cells
        if self.scope=='note':return {(self.model.channel,n,s) for n,s in cells}
        steps={s for n,s in cells}
        channels=range(9) if self.scope=='all_channels' else [self.model.channel]
        return {(c,n,s) for c in channels for n in range(128) for s in steps}
    def edit(self,n,s,on,paint=None):
        m=self.model
        preset=dict(m.pitch_presets[m.channel]);inserted=False
        for step in ([s%16+16*p for p in range(4)] if self.repeat_pages else [s]):
            if paint:
                cell=m.notes[n][step]
                if cell:
                    value=list(cell);value[0 if paint=='velocity' else 1]=m.velocity if paint=='velocity' else m.length
                    m.set_cell(m.pattern,m.channel,n,step,value)
            else:
                inserted=inserted or bool(on and m.notes[n][step] is None)
                m.pitch_presets[m.channel]=dict(preset);m.edit(n,step,on)
        if inserted:m.pitch_presets[m.channel]={'micro':0,'bend':0}
    def erase_rectangle(self,start,end):
        m=self.model;self.rectangle(start,end);m.begin()
        for n,s in self.selection:self.edit(n,s,False)
        self.rectangle(start,end)
        m.commit()
    def duplicate(self,count=None,to_end=False,to_left=False):
        m=self.model;length=m.lengths[m.pattern]
        start=min((s for n,s in self.selection),default=self.step)
        selected=self.selection.copy() if count is None and self.selection else None
        count=(max(s for n,s in selected)-start+1) if selected else (count or 1)
        count=min(count,length-start)
        if count<=0:return False
        dest=start-count if to_left else length-count if to_end else start+count
        if dest>=length:return False
        source=selected if selected is not None else {(m.selected,start+i) for i in range(count)}
        snapshot=[(c,n,s,m.patterns[m.pattern][c][n][s]) for c,n,s in sorted(self.targets(source))]
        m.begin()
        destinations=range(dest,length,count) if self.fill_to_end and not to_end and not to_left else [dest]
        pasted=set()
        for target in destinations:
            for c,n,s,value in snapshot:
                out=target+s-start
                if 0<=out<length:
                    m.set_cell(m.pattern,c,n,out,value)
                    if c==m.channel and (n,s) in source:pasted.add((n,out))
        if pasted:
            self.selection=pasted;self.step=min(s for n,s in pasted);m.select(max(n for n,s in pasted));m.page=self.step//16
        self.anchor=None;self.extent=None;self.scale_sessions.clear();m.commit();return bool(pasted)
    def scale(self,attribute,factor):
        """Scale a fixed selection snapshot, never compound repeated CC values."""
        m=self.model;index=0 if attribute=='velocity' else 1;lo,hi=(1,127) if index==0 else (15,300)
        key=(m.pattern,self.scope,tuple(sorted(self.targets())))
        session=self.scale_sessions.get(attribute)
        if session is None or session['key']!=key:
            original={(c,n,s):m.patterns[m.pattern][c][n][s][index] for c,n,s in self.targets() if m.patterns[m.pattern][c][n][s] is not None}
            session={'key':key,'original':original};self.scale_sessions[attribute]=session
        m.begin()
        for (c,n,s),base in session['original'].items():
            cell=m.patterns[m.pattern][c][n][s]
            if cell is None:continue
            updated=list(cell);updated[index]=max(lo,min(hi,round(base*factor)))
            m.set_cell(m.pattern,c,n,s,updated)
        m.commit()
