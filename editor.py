"""Grid navigation and editing transactions, independent of Tk and MIDI."""
class Editor:
    def __init__(self,model):
        self.model=model;self.step=0;self.selection=set();self.anchor=None
        self.scope='note';self.repeat_pages=False;self.scale_sessions={}
    def reset_selection(self):
        self.selection.clear();self.anchor=None;self.scale_sessions.clear()
    def rectangle(self,start,end):
        n0,s0=start;n1,s1=end
        self.selection={(n,s) for n in range(min(n0,n1),max(n0,n1)+1) for s in range(min(s0,s1),max(s0,s1)+1)}
        self.scale_sessions.clear()
    def move(self,dx=0,dy=0,extend=False):
        start=(self.model.selected,self.step)
        if extend:
            if self.anchor is None:self.anchor=start
        else:self.reset_selection()
        self.step=max(0,min(63,self.step+dx))
        self.model.select(max(0,min(127,self.model.selected+dy)))
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
    def edit(self,n,s,on):
        m=self.model
        for step in ([s%16+16*p for p in range(4)] if self.repeat_pages else [s]):m.edit(n,step,on)
    def erase_rectangle(self,start,end):
        m=self.model;self.rectangle(start,end);m.begin()
        for n,s in self.selection:self.edit(n,s,False)
        m.commit();m.select(end[0]);self.step=end[1]
    def duplicate(self,count,to_end=False):
        m=self.model;length=m.lengths[m.pattern];count=min(count,length-self.step)
        if count<=0:return False
        dest=length-count if to_end else self.step+count
        count=min(count,length-dest)
        if count<=0:return False
        source={(m.selected,self.step+i) for i in range(count)}
        snapshot=[(c,n,s,m.patterns[m.pattern][c][n][s]) for c,n,s in sorted(self.targets(source))]
        m.begin()
        for c,n,s,value in snapshot:m.set_cell(m.pattern,c,n,dest+s-self.step,value)
        m.commit();self.selection={(m.selected,dest+i) for i in range(count)}
        self.step=dest;m.page=dest//16;self.anchor=None;self.scale_sessions.clear();return True
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
