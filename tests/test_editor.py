import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import mido
from core import Model,Pickup,Clock,PADS2
from editor import Editor
from lighting import colors,default_theme,grid_color,blend
from app import App,DEFAULT
from helpers import headless_app

class Editing(unittest.TestCase):
    def setUp(self):self.m=Model();self.e=Editor(self.m)
    def test_navigation_wrap_and_extended_selection(self):
        self.e.page(-1);self.assertEqual((self.m.page,self.e.step),(3,48))
        self.e.page(1);self.assertEqual(self.e.step,0)
        self.e.move(2,1,True);self.assertEqual(self.e.selection,{(n,s) for n in (36,37) for s in (0,1,2)})
        self.e.move(1,0);self.assertFalse(self.e.selection)
    def test_duplicate_and_copy_to_last_steps(self):
        self.m.edit(36,0);self.m.edit(36,1);self.m.edit(37,0);self.m.select(36)
        self.assertTrue(self.e.duplicate(2));self.assertEqual(self.e.selection,{(36,2),(36,3)})
        self.assertIsNone(self.m.notes[37][2]);self.assertIsNotNone(self.m.notes[36][3])
        self.e.duplicate(2,True);self.assertEqual(self.e.step,62);self.assertIsNotNone(self.m.notes[36][63])
        self.m.history();self.assertIsNone(self.m.notes[36][63]);self.assertIsNotNone(self.m.notes[36][3])
    def test_all_channel_copy_and_scope_switches(self):
        self.m.set_cell(0,8,70,0,(80,250));self.e.toggle_channel_scope();self.assertEqual(self.e.scope,'all_channels')
        self.e.duplicate(1);self.assertEqual(self.m.patterns[0][8][70][1],(80,250))
        self.e.toggle_note_scope();self.assertEqual(self.e.scope,'note')
        self.e.toggle_note_scope();self.assertEqual(self.e.scope,'step')
        self.e.toggle_channel_scope();self.assertEqual(self.e.scope,'all_channels')
    def test_scaling_is_noncompounding_and_clamped(self):
        self.m.set_cell(0,0,36,0,(40,200));self.e.selection={(36,0),(37,0)}
        self.e.scale('velocity',2);self.assertEqual(self.m.notes[36][0],(80,200))
        self.e.scale('velocity',2);self.assertEqual(self.m.notes[36][0][0],80)
        self.e.scale('velocity',1);self.assertEqual(self.m.notes[36][0][0],40)
        self.e.scale('length',2);self.assertEqual(self.m.notes[36][0][1],300)
        self.e.scale('length',0);self.assertEqual(self.m.notes[36][0][1],15)
        self.assertIsNone(self.m.notes[37][0])
    def test_mirrored_writing_and_rectangle_undo(self):
        self.e.repeat_pages=True;self.m.begin();self.e.edit(36,3,True);self.m.commit()
        self.assertEqual([i for i,v in enumerate(self.m.notes[36]) if v],[3,19,35,51])
        self.m.history();self.assertFalse(any(self.m.notes[36]))
        self.m.history(True);self.e.repeat_pages=False
        self.e.erase_rectangle((35,2),(37,4));self.assertIsNone(self.m.notes[36][3]);self.assertIsNotNone(self.m.notes[36][19])
        self.m.history();self.assertIsNotNone(self.m.notes[36][3])
    def test_cycle_is_continuous_and_tint_only_affects_empty_gui_cells(self):
        theme=default_theme();theme['empty_length']=7;theme['empty']=['#110000','#220000','#330000','#440000','#550000','#660000','#770000']
        for page in range(4):
            self.m.page=page
            self.assertEqual(colors(self.m,theme,10)[:16],[theme['empty'][(page*16+i)%7] for i in range(16)])
        theme['grid_tint']=0;self.assertEqual(grid_color(theme,20,None),'#101722')
        theme['grid_tint']=100;self.assertEqual(grid_color(theme,20,None),theme['empty'][6])
        self.assertEqual(grid_color(theme,20,(127,100)),theme['high'])

class ForcedPickup(unittest.TestCase):
    def test_sustained_fast_away_turn_overrides_in_both_directions(self):
        for start,target,direction in ((70,100,-1),(60,20,1)):
            clock=[0.0];p=Pickup(lambda:clock[0]);self.assertIsNone(p.value('x',start,target,1,127))
            got=None
            for i in range(1,9):
                clock[0]=i*.05;result=p.value('x',start+direction*2*i,target,1,127)
                if i<6:self.assertIsNone(result)
                if result is not None:self.assertGreater((result-target)*direction,0);target=result;got=result
            self.assertIsNotNone(got)
    def test_slow_turn_pauses_and_direction_changes_do_not_force(self):
        clock=[0.0];p=Pickup(lambda:clock[0]);p.value('x',60,110,1,127)
        for i in range(1,9):
            clock[0]=i*.1;self.assertIsNone(p.value('x',60-i,110,1,127))
        p.reset();clock[0]=0;p.value('x',60,110,1,127)
        for i,raw in enumerate((56,52,54,50,46,48,44),1):
            clock[0]=i*.05;self.assertIsNone(p.value('x',raw,110,1,127))
        clock[0]=2;self.assertIsNone(p.value('x',42,110,1,127))

class ControlRouting(unittest.TestCase):
    def setUp(self):
        self.a=headless_app()
    def note(self,ch,n,velocity=100):self.a.midi(1,mido.Message('note_on',channel=ch-1,note=n,velocity=velocity))
    def test_hold_undo_redoes_without_first_undoing(self):
        a=self.a;a.model.edit(36,0);a.model.history()
        with patch('app.time.monotonic',return_value=10):self.note(11,PADS2[15])
        self.assertIsNone(a.model.notes[36][0])
        with patch('app.time.monotonic',return_value=11.1):self.note(11,PADS2[15],0)
        self.assertIsNotNone(a.model.notes[36][0])
    def test_paint_gate_preserves_velocity_and_does_not_add_notes(self):
        a=self.a;a.model.edit(36,0);a.model.edit(37,0);a.model.select(36)
        a.action('paint_gate');a.model.length=250;a.model.velocity=30
        a.click(SimpleNamespace(x=81,y=349,state=0),False);a.drag(SimpleNamespace(x=879,y=31),3);a.end_stroke(3)
        self.assertEqual(a.model.notes[36][0],(100,250));self.assertEqual(a.model.notes[37][0],(100,100))
        self.assertEqual(sum(bool(c) for c in a.model.notes[36]),1)
        a.model.history();self.assertEqual(a.model.notes[36][0],(100,100))
    def test_bank_routing_and_fader_does_not_touch_other_parameters(self):
        a=self.a;a.model.edit(36,0);a.model.edit(36,7)
        a.midi(1,mido.Message('control_change',channel=5,control=48,value=101))
        self.assertEqual(a.model.notes[36][0][1],100)
        a.midi(1,mido.Message('control_change',channel=5,control=56,value=39))
        a.midi(1,mido.Message('control_change',channel=5,control=56,value=42))
        self.assertEqual(a.encoder_attribute,'length');self.assertGreater(a.model.notes[36][0][1],100)
        a.midi(1,mido.Message('control_change',channel=5,control=55,value=101));self.assertEqual(a.model.bpm,120)
        a.midi(1,mido.Message('control_change',channel=0,control=67,value=43));a.midi(1,mido.Message('control_change',channel=0,control=67,value=46));self.assertGreater(a.model.bpm,120)
    def test_shift_mouse_rectangle_does_not_paint_until_erase_release(self):
        a=self.a;a.model.edit(36,0);a.model.edit(37,1)
        a.click(SimpleNamespace(x=81,y=349,state=1),False)
        a.drag(SimpleNamespace(x=150,y=310),3)
        self.assertIsNotNone(a.model.notes[36][0]);a.end_stroke(3)
        self.assertIsNone(a.model.notes[36][0]);self.assertIsNone(a.model.notes[37][1]);a.model.history();self.assertIsNotNone(a.model.notes[37][1])

class Audition(unittest.TestCase):
    def test_pattern_length_loops_and_retains_hidden_notes(self):
        m=Model();m.lengths[0]=8;m.edit(36,8);events=[]
        c=Clock(m,lambda kind,**kw:events.append((kind,kw)))
        try:
            with c.lock:
                c.running=True;c.tick=8*6;c.next=100;c.advance(100)
                self.assertEqual(c.step,0);self.assertFalse(any(t=='note_on' for t,k in events))
                self.assertIsNotNone(m.notes[36][8])
                restored=Model();restored.load(m.dump());self.assertEqual(restored.lengths[0],8)
                e=Editor(m);m.edit(36,0);e.duplicate(1,True);self.assertIsNotNone(m.notes[36][7])
        finally:c.close()
    def test_live_note_off_does_not_cut_sequencer_note(self):
        events=[];c=Clock(Model(),lambda kind,**kw:events.append((kind,kw)))
        try:
            with c.lock:
                c.active.add((0,36));c.audition_on(0,36,90);c.audition_off(0,36)
                self.assertFalse(any(t=='note_off' for t,kw in events));c.release();self.assertEqual(events[-1][0],'note_off')
                c.audition_on(1,50,80);c.release_live();self.assertFalse(c.live);self.assertEqual(events[-1][1]['note'],50)
        finally:c.close()
