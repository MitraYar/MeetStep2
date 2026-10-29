"""Step input and bounded, per-pass live recording state."""
import time

class NoteInput:
    def __init__(self,app):
        self.app=app;self.step=False;self.sticky=False;self.record=False;self.hotkeys=False
        self.deadline=None;self.routes={};self.collisions={};self.pass_key=None;self.held={}
    def poll(self,now=None):
        now=time.perf_counter() if now is None else now
        clock=self.app.clock;key=(clock.model.playing,clock.cycle_id,clock.running)
        if key!=self.pass_key:
            if clock.running:
                self.collisions={k:v for k,v in self.collisions.items() if k[1]>=clock.cycle_id and k[0] in (clock.model.playing,clock.queued)}
            else:self.collisions.clear()
            self.pass_key=key
    def cell(self,c,velocity):
        a=self.app;m=a.model;meta=a.pitch_controls.preset(c)
        if a.editor.articulation:meta['mode']=a.editor.articulation
        a.pitch_controls.consume(c)
        return (velocity,m.length,meta) if any(meta.values()) else (velocity,m.length)
    def press(self,source,channel,note,velocity,at):
        a=self.app;m=a.model;c=m.channel if self.hotkeys else channel
        holds=[v for v in a.step_holds.values() if (v['pattern'],v['channel'])==(m.pattern,c)]
        selected={s for n,s in a.editor.selection} if m.channel==c else set()
        fresh=not any(v[0]==c for v in self.held.values())
        self.held[source,channel,note]=(c,note,velocity)
        if a.follow_keys:
            if m.channel!=c or m.selected!=note:
                a.cancel_stroke();a.reset_faders()
                if not holds and not (m.mono[c] and selected):a.editor.reset_selection()
            m.channel=c;m.select(note)
        if a.drone_mode:
            m.set_meta('drones',(m.pattern,c,note),not m.drones[m.pattern][c][note])
        elif (holds or selected) and m.mono[c]:
            m.begin()
            for s in selected|{h['step'] for h in holds}:
                old=m.step_note(s,c);value=m.patterns[m.pattern][c][old][s] or self.cell(c,velocity)
                m.write_cell(m.pattern,c,note,s,value);a.editor.selection.discard((old,s));a.editor.selection.add((note,s))
            for hold in holds:hold['note']=note;hold['selected']=True
            m.commit()
        elif self.record and a.clock.running:self.record_note(c,note,velocity,at)
        elif self.step:
            m.begin()
            if fresh and not self.sticky:self.clear_step(c)
            m.write_cell(m.pattern,c,note,a.editor.step,self.cell(c,velocity));m.commit()
        if a.audition and not a.drone_mode:
            if (c,note) not in self.routes.values():a.clock.audition_on(c,note,velocity)
            self.routes[source,channel,note]=(c,note)
    def release(self,source,channel,note):
        self.held.pop((source,channel,note),None)
        target=self.routes.pop((source,channel,note),None)
        if target and target not in self.routes.values():self.app.clock.audition_off(*target)
    def clear_step(self,c):
        m=self.app.model;s=self.app.editor.step
        for n,row in enumerate(m.patterns[m.pattern][c]):
            if row[s]:m.set_cell(m.pattern,c,n,s,None)
    def moved(self):
        """A held chord survives any delay; only J/L commits it at another step."""
        if not self.step or not self.held:return
        a=self.app;m=a.model;m.begin()
        if not self.sticky:
            for c in {v[0] for v in self.held.values()}:self.clear_step(c)
        # One pending pitch preset covers the entire chord, not just its first note.
        presets={c:a.pitch_controls.preset(c) for c,_,_ in self.held.values()}
        for c,n,v in self.held.values():
            m.pitch_presets[c]=presets[c].copy();m.write_cell(m.pattern,c,n,a.editor.step,self.cell(c,v))
        m.commit()
    def disconnect(self,source):
        for key in list(self.held):
            if key[0]==source:self.release(*key)
        for key in list(self.routes):
            if key[0]==source:self.release(*key)
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
