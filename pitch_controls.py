"""Pending, held and paint-only pitch modifiers; cell articulation stays intact."""
import copy

class PitchControls:
    def __init__(self,app):
        self.app=app;self.mode=False;self.held=set();self.used=set();self.reset_held=False
    def component(self,number):return 'approach' if number<5 else 'micro'
    def enable(self,preset,number):
        config=self.app.config['pitch']
        if number<5:preset.update(bend=number,approach=copy.deepcopy(config['approach'][number-1]))
        else:
            micro=config['micro'][number-5];preset.update(micro=micro['cents'],micro_ms=micro['ms'],micro_key=number)
    def preset(self,c):
        preset=copy.deepcopy(self.app.model.pitch_presets[c])
        for number in sorted(self.held):self.enable(preset,number)
        return preset
    def consume(self,c):
        self.used|=self.held
        if self.mode:return
        preset={'micro':0,'bend':0}
        for number in sorted(self.held):self.enable(preset,number)
        self.app.model.pitch_presets[c]=preset
    def release(self,number):
        self.held.discard(number)
        if number in self.used and not self.mode:
            for preset in self.app.model.pitch_presets:
                if number<5 and preset.get('bend')==number:preset['bend']=0;preset.pop('approach',None)
                elif number>=5 and preset.get('micro_key')==number:preset.update(micro=0,micro_key=0);preset.pop('micro_ms',None)
        self.used.discard(number)
    def toggle(self,number):
        a=self.app;m=a.model;preset=m.pitch_presets[m.channel]
        active=preset.get('bend')==number if number<5 else preset.get('micro_key')==number
        if active and number not in self.held:
            if number<5:preset['bend']=0;preset.pop('approach',None)
            else:preset.update(micro=0,micro_key=0);preset.pop('micro_ms',None)
        else:self.enable(preset,number)
        m.begin()
        for n,s in a.editor.selection:m.set_pitch(n,s,preset,self.component(number))
        m.commit();a.clock.refresh_live_pitch(m.channel)
    def reset(self):
        a=self.app;m=a.model;m.begin()
        for n,s in a.editor.selection:m.set_pitch(n,s,{})
        m.commit();m.pitch_presets=[{'micro':0,'bend':0} for _ in range(9)]
        with a.clock.lock:a.clock.pitch.reset()
    def paint(self,n,s,reset=False):
        m=self.app.model;m.set_pitch(n,s,{} if reset else self.preset(m.channel))
        if not reset:self.used|=self.held
