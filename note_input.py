"""Step input and bounded, per-pass live recording state."""
import time

class NoteInput:
    def __init__(self,app):
        self.app=app;self.step=False;self.sticky=False;self.record=False;self.hotkeys=False
        self.deadline=None;self.routes={};self.collisions={};self.pass_key=None
    def poll(self,now=None):
        now=time.perf_counter() if now is None else now
        if self.deadline is not None and now>=self.deadline:
            self.deadline=None;self.app.navigate(1,0)
        clock=self.app.clock;key=(clock.model.playing,clock.cycle_id,clock.running)
        if key!=self.pass_key:
            if clock.running:
                self.collisions={k:v for k,v in self.collisions.items() if k[1]>=clock.cycle_id and k[0] in (clock.model.playing,clock.queued)}
            else:self.collisions.clear()
            self.pass_key=key
    def cell(self,c,velocity):
        a=self.app;m=a.model;meta=dict(m.pitch_presets[c])
        if a.editor.articulation:meta['mode']=a.editor.articulation
        m.pitch_presets[c]={'micro':0,'bend':0}
        return (velocity,m.length,meta) if any(meta.values()) else (velocity,m.length)
    def press(self,source,channel,note,velocity,at):
        a=self.app;m=a.model;c=m.channel if self.hotkeys else channel
        holds=[v for v in a.step_holds.values() if (v['pattern'],v['channel'])==(m.pattern,c)]
        if a.follow_keys:
            if m.channel!=c or m.selected!=note:
                a.cancel_stroke();a.reset_faders()
                if not holds:a.editor.reset_selection()
            m.channel=c;m.select(note)
        if a.drone_mode:
            m.set_meta('drones',(m.pattern,c,note),not m.drones[m.pattern][c][note])
        elif holds and m.mono[c]:
            m.begin()
            for hold in holds:
                s=hold['step'];old=m.step_note(s,c);value=m.patterns[m.pattern][c][old][s] or self.cell(c,velocity)
                m.write_cell(m.pattern,c,note,s,value);a.editor.selection.discard((old,s));a.editor.selection.add((note,s))
                hold['note']=note;hold['selected']=True
            m.commit()
        elif self.record and a.clock.running:self.record_note(c,note,velocity,at)
        elif self.step:
            m.begin();m.write_cell(m.pattern,c,note,a.editor.step,self.cell(c,velocity));m.commit()
            if not self.sticky and self.deadline is None:self.deadline=at+.3
        if a.audition and not a.drone_mode:
            if (c,note) not in self.routes.values():a.clock.audition_on(c,note,velocity)
            self.routes[source,channel,note]=(c,note)
    def release(self,source,channel,note):
        target=self.routes.pop((source,channel,note),None)
        if target and target not in self.routes.values():self.app.clock.audition_off(*target)
    def record_note(self,c,n,v,at):
        a=self.app;m=a.model;self.poll(at);p,cycle,s=a.clock.quantize(at)
        key=(p,cycle,c,s);previous=self.collisions.get(key)
        m.begin()
        if previous is None:
            m.write_cell(p,c,n,s,self.cell(c,v));self.collisions[key]={'last':None}
        else:
            # First onset stays. A third and later onset replaces the middle one.
            if previous['last']:
                old_n,old_s,original=previous['last'];m.set_cell(p,c,old_n,old_s,original)
            target=(s+1)%m.lengths[p];original=m.patterns[p][c][n][target]
            m.write_cell(p,c,n,target,self.cell(c,v));previous['last']=(n,target,original)
        m.commit()
