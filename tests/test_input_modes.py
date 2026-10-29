import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import mido
from core import Model,ScaleTakeover,PADS
from lighting import colors,default_theme
from pitch import PitchEngine,duration
from preferences import normalize_settings
from helpers import headless_app,manual_clock

class InputModes(unittest.TestCase):
    def setUp(self):
        self.a=headless_app();self.events=[];self.a.clock=manual_clock(self.a.model,self.events)
    def tearDown(self):self.a.clock.close()
    def event(self,x=81,y=340,state=0):return SimpleNamespace(x=x,y=y,state=state)
    def note(self,n,ch=0,on=True,at=10):
        self.a.midi(1,mido.Message('note_on' if on else 'note_off',channel=ch,note=n,velocity=90 if on else 0),at)
    def test_select_mode_rectangle_click_and_right_clear_never_edit(self):
        a=self.a;a.model.edit(36,0);a.action('select_mode')
        a.click(self.event());a.drag(self.event(150,310),1);a.end_stroke(1)
        self.assertEqual(a.editor.selection,{(36,0),(36,1),(37,0),(37,1)})
        a.click(self.event(),False);self.assertFalse(a.editor.selection);self.assertTrue(a.select_mode)
        self.assertIsNotNone(a.model.notes[36][0]);a.click(self.event());a.end_stroke(1)
        self.assertFalse(a.editor.selection);self.assertEqual(sum(bool(c) for r in a.model.notes for c in r),1)
    def test_header_hold_then_control_shift_and_delete_selection(self):
        a=self.a;a.model.edit(36,63);a.model.edit(38,3)
        with patch('gestures.time.monotonic',return_value=10):a.click(self.event(40))
        with patch('gestures.time.monotonic',return_value=10.6):a.gestures.poll()
        a.end_stroke(1);self.assertEqual(a.editor.selection,{(36,s) for s in range(64)})
        a.click(self.event(40,320,4));self.assertIn((37,63),a.editor.selection)
        a.click(self.event(40,280,1));self.assertIn((39,0),a.editor.selection)
        a.action('delete_selection');self.assertFalse(any(c for r in a.model.notes for c in r))
        a.action('undo');self.assertIsNotNone(a.model.notes[36][63]);self.assertIsNotNone(a.model.notes[38][3])
    def test_relative_velocity_locked_row_and_right_absolute(self):
        a=self.a;m=a.model;m.set_cell(0,0,36,0,(80,100));m.set_cell(0,0,36,1,(50,100));m.set_cell(0,0,37,1,(70,200))
        a.action('paint_velocity');a.click(self.event());self.assertEqual(m.notes[36][0][0],80)
        a.drag(self.event(150,300),1);self.assertGreater(m.notes[36][0][0],80);self.assertGreater(m.notes[36][1][0],50)
        a.drag(self.event(81,380),1);self.assertLess(m.notes[36][0][0],80);self.assertEqual(m.notes[37][1],(70,200));a.end_stroke(1)
        m.velocity=22;a.click(self.event(),False);a.drag(self.event(150,100),3);a.end_stroke(3)
        self.assertEqual([m.notes[36][s][0] for s in (0,1)],[22,22])
    def test_mouse_held_faders_are_absolute_after_new_cc(self):
        a=self.a;a.model.edit(36,0);a.action('paint_gate');a.click(self.event())
        a.fader('length',127);self.assertEqual(a.model.notes[36][0][1],300)
        a.fader('velocity',0);self.assertEqual(a.model.notes[36][0][0],1)
        a.end_stroke(1);a.action('undo');self.assertEqual(a.model.notes[36][0],(100,100))
    def test_drone_right_click_header_and_cell(self):
        a=self.a
        for x in (40,81):
            a.model.set_meta('drones',(0,0,36),True);a.click(self.event(x),False);a.end_stroke(3)
            self.assertFalse(a.model.drones[0][0][36])
    def test_articulation_is_per_cell_and_brush_persists(self):
        a=self.a;a.action('legato');a.click(self.event());a.end_stroke(1)
        self.assertEqual(a.editor.articulation,'legato');self.assertEqual(a.model.notes[36][0][2]['mode'],'legato')
        a.action('nonlegato');a.click(self.event(150));a.end_stroke(1)
        self.assertEqual(a.model.notes[36][0][2]['mode'],'legato');self.assertEqual(a.model.notes[36][1][2]['mode'],'nonlegato')
        a.action('cancel_articulation');a.click(self.event());a.end_stroke(1)
        self.assertEqual(a.model.notes[36][0][2]['mode'],'gate');self.assertEqual(a.model.notes[36][1][2]['mode'],'nonlegato')
        restored=Model();restored.load(json.loads(json.dumps(a.model.dump())));self.assertEqual(restored.notes[36],a.model.notes[36])
    def test_pad_hold_toggles_sticky_selection_and_clears_articulation(self):
        a=self.a;a.model.edit(36,0,articulation='legato')
        for at in (10,12):
            with patch('app.time.monotonic',return_value=at):self.note(PADS[0],9)
            with patch('app.time.monotonic',return_value=at+.6):self.note(PADS[0],9,False)
            self.assertEqual(bool(a.editor.selection),at==10)
        a.action('cancel_articulation')
        with patch('app.time.monotonic',return_value=14):self.note(PADS[0],9)
        with patch('app.time.monotonic',return_value=14.6):self.note(PADS[0],9,False)
        self.assertEqual(a.model.notes[36][0][2]['mode'],'gate')
    def test_mono_collapses_selected_or_lowest_and_undo_restores(self):
        a=self.a;m=a.model
        for p,notes in [(0,(36,40)),(7,(50,55))]:
            for n in notes:m.set_cell(p,0,n,0,(100,100))
        m.select(40);a.action('mono');self.assertIsNone(m.notes[36][0]);self.assertIsNotNone(m.notes[40][0])
        self.assertIsNotNone(m.patterns[7][0][50][0]);self.assertIsNone(m.patterns[7][0][55][0])
        a.action('undo');self.assertFalse(m.mono[0]);self.assertIsNotNone(m.notes[36][0]);self.assertIsNotNone(m.patterns[7][0][55][0])
    def test_mono_pad_hold_transposes_and_all_notes_reach_leds_and_knobs(self):
        a=self.a;m=a.model;m.edit(36,0);m.edit(42,1);m.select(36);a.action('mono')
        self.note(PADS[0],9);self.note(64);self.note(PADS[0],9,False)
        self.assertIsNone(m.notes[36][0]);self.assertIsNotNone(m.notes[64][0]);self.assertIn((64,0),a.editor.selection)
        palette=colors(m,default_theme(),10);self.assertNotEqual(palette[1],'#000000')
        a.knob('length',1,20,'gate1');a.knob('length',1,40,'gate1');self.assertGreater(m.notes[42][1][1],100)
        self.assertEqual(sum(bool(row[0]) for row in m.notes),1)
    def test_t_fills_only_selected_empty_cells(self):
        a=self.a;a.model.set_cell(0,0,36,0,(20,200));a.editor.selection={(36,0),(36,1),(37,1)}
        a.editor.scope='all_channels'
        a.action('insert_selection');self.assertEqual(a.model.notes[36][0],(20,200))
        self.assertIsNotNone(a.model.notes[36][1]);self.assertIsNotNone(a.model.notes[37][1]);self.assertIsNone(a.model.notes[37][0])
        self.assertIsNone(a.model.patterns[0][1][36][1]);self.assertIsNone(a.model.notes[38][1])
    def test_step_input_held_chord_manual_advance_and_sticky(self):
        a=self.a;a.action('step_input');self.note(36,at=10);self.note(40,at=10.2)
        a.note_input.poll(130);self.assertEqual(a.editor.step,0)
        self.assertIsNotNone(a.model.notes[36][0]);self.assertIsNotNone(a.model.notes[40][0])
        a.action('grid_right');self.assertEqual(a.editor.step,1)
        self.assertIsNotNone(a.model.notes[36][1]);self.assertIsNotNone(a.model.notes[40][1])
        a.action('sticky_input');self.note(43,at=11);self.note(47,at=12);a.note_input.poll(20)
        self.assertEqual(a.editor.step,1);self.assertIsNotNone(a.model.notes[47][1])
        a.action('grid_right');self.assertEqual(a.editor.step,2)
    def test_record_any_pitch_collision_drops_middle_and_frees_pass(self):
        a=self.a;c=a.clock;c.running=True;c.tick=0;c.next=10;c.advance(10);a.action('record_input')
        for n,t in ((36,10.01),(40,10.02),(43,10.03)):self.note(n,at=t)
        self.assertIsNotNone(a.model.notes[36][0]);self.assertIsNone(a.model.notes[40][1]);self.assertIsNotNone(a.model.notes[43][1])
        self.assertEqual(len(a.note_input.collisions),1)
        c.tick=64*6;c.next=18;c.advance(18);a.note_input.poll(18);self.assertFalse(a.note_input.collisions)
    def test_hotkey_mode_ignores_input_channel_but_releases_original_route(self):
        a=self.a;a.action('channel_hotkey_6');a.action('hotkey_mode');a.audition=True
        self.note(60,2);a.action('channel_hotkey_4');self.note(60,2,False)
        ons=[kw for typ,kw in self.events if typ=='note_on'];offs=[kw for typ,kw in self.events if typ=='note_off']
        self.assertEqual((ons[-1]['channel'],offs[-1]['channel']),(6,6));self.assertEqual(a.model.channel,4)
    def test_copy_shortcuts_preserve_view_and_double_copy_all(self):
        a=self.a;m=a.model;m.channel=2;m.edit(36,0);m.set_cell(0,4,60,2,(90,130));m.lengths[0]=26
        with patch('app.time.monotonic',return_value=10):a.action('copy_pattern_3')
        self.assertIsNotNone(m.patterns[3][2][36][0]);self.assertIsNone(m.patterns[3][4][60][2])
        with patch('app.time.monotonic',return_value=10.2):a.action('copy_pattern_3')
        self.assertEqual((m.pattern,m.channel,m.lengths[3]),(0,2,26));self.assertIsNotNone(m.patterns[3][4][60][2])
        a.action('copy_note_5');self.assertIsNotNone(m.patterns[5][2][36][0]);self.assertEqual(m.pattern,0)
    def test_clear_pattern_preserves_current_channel(self):
        a=self.a;a.model.channel=4;a.model.edit(36,0)
        with patch('app.time.monotonic',return_value=10):a.action('delete_channel_0')
        self.assertEqual(a.model.channel,4)
        with patch('app.time.monotonic',return_value=10.1):a.action('delete_channel_0')
        self.assertEqual(a.model.channel,4);self.assertIsNone(a.model.notes[36][0])

class SwingPitchScale(unittest.TestCase):
    def test_scale_moves_immediately_after_anchor_without_crossing(self):
        s=ScaleTakeover();self.assertIsNone(s.value('gate',100,100,15,300))
        value=s.value('gate',90,100,15,300);self.assertLess(value,100)
        value=s.value('gate',0,value,15,300);self.assertEqual(value,15)
        self.assertEqual(s.value('gate',127,value,15,300),300)
    def test_swing_is_straight_clock_with_delayed_odd_steps(self):
        m=Model();m.swing=100;m.edit(36,0);m.edit(40,1);m.edit(43,2);events=[];c=manual_clock(m,events)
        try:
            c.running=True;c.next=10;c.advance(10);c.tick=6;c.next=10.125;c.advance(10.125)
            self.assertEqual(c.step,0);c.advance(10+1/6+.00001);self.assertEqual(c.step,1)
            c.tick=12;c.next=10.25;c.advance(10.25);self.assertEqual(c.step,2)
            self.assertAlmostEqual(c.step_seconds(0)/c.step_seconds(1),2)
            m.lengths[0]=3;self.assertAlmostEqual(sum(c.step_seconds(s) for s in range(3)),.375)
            self.assertEqual(c.quantize(10.245)[2],2)
        finally:c.close()
    def test_fraction_ms_micro_transition_and_curve_shape(self):
        self.assertAlmostEqual(duration('1\\16',120),.125);self.assertAlmostEqual(duration('120',120),.12)
        rng=SimpleNamespace(uniform=lambda a,b:0);p=PitchEngine(lambda *args,**kwargs:None,rng)
        p.start(0,{'micro':50,'micro_ms':200},10,120);self.assertAlmostEqual(p.cents(0,10.1),25)
        p.update(10.2);self.assertAlmostEqual(p.cents(0,11),50)
        for c,curve in ((1,0),(2,100)):
            p.start(c,{'bend':1,'approach':{'start':30,'random':0,'time':'120','curve':curve}},10,120)
        self.assertGreater(p.cents(1,10.06),p.cents(2,10.06))
    def test_v4_note_articulation_migrates_to_each_cell(self):
        m=Model();m.edit(36,0);m.edit(36,4);data=m.dump();data['version']=4;data['note_modes']=m.note_modes;data['note_modes'][0][0][36]='legato'
        restored=Model();restored.load(data)
        self.assertEqual(restored.notes[36][0][2]['mode'],'legato');self.assertEqual(restored.notes[36][4][2]['mode'],'legato')
    def test_pitch_settings_export_round_trip_and_invalid_time(self):
        from app import DEFAULT
        data=copy.deepcopy(DEFAULT);data['pitch']['micro'][0]={'cents':-42,'ms':180};data['pitch']['approach'][2]['time']='1\\128'
        self.assertEqual(normalize_settings(json.loads(json.dumps(data)))['pitch'],data['pitch'])
        data['pitch']['approach'][0]['time']='1/0'
        with self.assertRaises(ValueError):normalize_settings(data)

if __name__=='__main__':unittest.main()
