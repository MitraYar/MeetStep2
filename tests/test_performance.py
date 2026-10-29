import copy
import json
import random
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import mido
from core import Model,PADS,PADS2
from editor import Editor
from pitch import PitchEngine
from preferences import normalize_settings
from shortcuts import key_id,pretty_key
from app import DEFAULT
from helpers import headless_app,manual_clock

class MusicalPlayback(unittest.TestCase):
    def setUp(self):
        self.m=Model();self.events=[];self.c=manual_clock(self.m,self.events)
    def tearDown(self):self.c.close()
    def tick(self,step,now):
        self.c.running=True;self.c.tick=step*6;self.c.next=now;self.c.advance(now)
    def notes(self,kind):return [(kw['channel'],kw['note']) for t,kw in self.events if t==kind]
    def test_queued_switch_waits_for_actual_pattern_length(self):
        self.m.lengths[0]=3;self.m.set_cell(0,0,36,2,(80,100));self.m.set_cell(1,1,60,0,(100,100))
        self.tick(1,10);self.c.switch_pattern(1);self.assertEqual(self.m.playing,0)
        self.tick(2,10.125);self.assertIn((0,36),self.notes('note_on'))
        self.tick(3,10.25);self.assertEqual((self.m.playing,self.c.step,self.c.queued),(1,0,None))
        self.assertIn((1,60),self.notes('note_on'))
    def test_shared_drone_survives_switch_and_stop_releases_it(self):
        self.m.drones[0][2][48]=True;self.m.drones[1][2][48]=True;self.m.drones[1][3][60]=True
        self.c.sync_drones();self.assertFalse(self.notes('note_on'))
        self.tick(0,10);self.c.switch_pattern(1,True)
        self.assertEqual(self.notes('note_on').count((2,48)),1);self.assertNotIn((2,48),self.notes('note_off'))
        self.assertIn((3,60),self.notes('note_on'));self.c.stop()
        self.assertEqual(set(self.notes('note_off')),{(2,48),(3,60)});self.assertFalse(self.c.drone_active)
    def test_mutes_release_sequence_but_preserve_live_audition(self):
        self.m.edit(36,0);self.tick(0,10);self.c.audition_on(0,36,90)
        self.c.mute(0,True);self.assertNotIn((0,36),self.notes('note_off'))
        self.assertFalse(self.c.active);self.c.audition_off(0,36);self.assertIn((0,36),self.notes('note_off'))
        self.events.clear();self.tick(0,11);self.assertFalse(self.notes('note_on'))
        self.c.audition_on(0,42,90);self.assertEqual(self.notes('note_on'),[(0,42)])
    def test_legato_ties_even_if_timer_is_late(self):
        self.m.edit(36,0,articulation='legato');self.m.edit(36,1,articulation='legato')
        self.tick(0,10);self.tick(1,10.14)
        self.assertEqual(self.notes('note_on'),[(0,36)]);self.assertFalse(self.notes('note_off'))
        self.assertIn((0,36),self.c.active)
    def test_legato_chords_overlap_and_nonlegato_leaves_gap(self):
        for note in (36,40):self.m.edit(note,0,articulation='legato')
        self.m.edit(43,1);self.tick(0,10);self.tick(1,10.125)
        self.assertEqual(set(self.notes('note_on')),{(0,36),(0,40),(0,43)});self.assertFalse(self.notes('note_off'))
        self.c.advance(10.1271);self.assertEqual(set(self.notes('note_off')),{(0,36),(0,40)})
        self.c.stop();self.events.clear();self.m.set_articulation(36,0,'nonlegato');self.m.set_articulation(40,0,'nonlegato')
        self.tick(0,20);deadline=20+.125-.5/32
        self.c.advance(deadline-.0001);self.assertFalse(self.notes('note_off'))
        self.c.advance(deadline+.0001);self.assertEqual(set(self.notes('note_off')),{(0,36),(0,40)})
        self.tick(1,20.125);self.assertIn((0,43),self.notes('note_on'))
    def test_pitchwheel_only_routes_to_live_channels_and_combines_micro(self):
        self.m.pitch_presets[4]={'micro':22,'bend':0};self.c.audition_on(4,60,90);self.c.audition_on(6,62,80)
        self.events.clear();self.c.input_pitch(1000)
        bends={kw['channel']:kw['pitch'] for t,kw in self.events if t=='pitchwheel'}
        self.assertEqual(bends,{4:1000+round(22*8192/200),6:1000});self.assertNotIn(0,bends)
        self.c.audition_off(4,60);self.events.clear();self.c.input_pitch(2000)
        self.assertEqual({kw['channel'] for t,kw in self.events if t=='pitchwheel'},{6})

class PitchAndEditing(unittest.TestCase):
    def test_bend_random_ranges_durations_and_combination(self):
        for bend in range(1,5):
            events=[];p=PitchEngine(lambda kind,**kw:events.append((kind,kw)),random.Random(45))
            p.start(3,{'micro':-68,'bend':bend},10,120)
            curve=p.curves[3];start,duration,amount,micro=[curve[k] for k in ('start','duration','amount','micro')]
            self.assertTrue(25<=abs(amount)<=35);self.assertEqual(amount>0,bend<3)
            expected=.5/(4 if bend in (1,3) else 12);self.assertLessEqual(abs(duration-expected),.03)
            self.assertIn(('control_change',{'channel':3,'control':6,'value':2}),events)
            self.assertEqual(events[-1][1]['pitch'],round((-68+amount)*8192/200))
            p.update(11);self.assertEqual(events[-1][1]['pitch'],round(-68*8192/200))
    def test_insert_consumes_pitch_preset_and_project_round_trip(self):
        m=Model();e=Editor(m);m.pitch_presets[0]={'micro':22,'bend':3};e.repeat_pages=True;e.edit(36,2,True)
        for s in (2,18,34,50):self.assertEqual(m.notes[36][s][2],{'micro':22,'bend':3})
        self.assertEqual(m.pitch_presets[0],{'micro':0,'bend':0})
        m.drones[7][8][127]=True;m.patterns[3][2][60][0]=(100,100,{'mode':'nonlegato'});m.muted[4]=True;m.bases[8]=15
        restored=Model();restored.load(json.loads(json.dumps(m.dump())));self.assertEqual(restored.dump(),m.dump())
    def test_existing_cell_keeps_values_and_preserves_pending_pitch(self):
        m=Model();m.edit(36,0);m.velocity=20;m.length=230;m.pitch_presets[0]['micro']=-50
        m.edit(36,0,True);self.assertEqual(m.notes[36][0],(100,100));self.assertEqual(m.pitch_presets[0]['micro'],-50)
    def test_duplicate_rectangle_cursor_and_history_restore_channel(self):
        m=Model();e=Editor(m);m.channel=3;m.set_cell(0,3,36,2,(50,130));m.set_cell(0,3,37,3,(70,250))
        e.rectangle((36,2),(37,3));self.assertEqual((e.step,m.selected),(2,37));e.duplicate()
        self.assertEqual((m.notes[36][4],m.notes[37][5]),((50,130),(70,250)))
        m.channel=8;m.pattern=4;e.step=30;m.history()
        self.assertEqual((m.pattern,m.channel,e.step,m.selected),(0,3,2,37));self.assertIsNone(m.notes[36][4])
        m.history(True);self.assertEqual((e.step,m.selected),(4,37))
    def test_left_copy_truncates_first_items_and_fill_repeats_snapshot(self):
        m=Model();e=Editor(m)
        for s,v in enumerate((40,50,60),1):m.set_cell(0,0,36,s,(v,100))
        e.step=1;e.duplicate(3,to_left=True);self.assertEqual(m.notes[36][0][0],60)
        e.reset_selection();e.step=1;m.lengths[0]=8;e.fill_to_end=True;e.duplicate(3)
        self.assertEqual([m.notes[36][s][0] for s in range(4,8)],[40,50,60,40])
    def test_per_channel_offsets_and_c1_bottom(self):
        a=headless_app();self.assertEqual(a.model.base,36);a.action('offset_up');a.action('offset_up')
        a.select_channel(1);self.assertEqual(a.model.base,36);a.select_channel(0);self.assertEqual(a.model.base,38)

class HardwareAndSettings(unittest.TestCase):
    def setUp(self):self.a=headless_app()
    def note(self,ch,n,velocity=100,source=1):
        self.a.midi(source,mido.Message('note_on',channel=ch-1,note=n,velocity=velocity))
    def test_hold_step_selects_without_toggle_and_tap_toggles(self):
        a=self.a;a.model.edit(36,0)
        with patch('app.time.monotonic',return_value=10):self.note(10,PADS[0]);self.note(10,PADS[1])
        with patch('app.time.monotonic',return_value=10.6):self.note(10,PADS[0],0);self.note(10,PADS[1],0)
        self.assertEqual(a.editor.selection,{(36,0),(36,1)});self.assertIsNotNone(a.model.notes[36][0]);self.assertIsNone(a.model.notes[36][1])
        with patch('app.time.monotonic',return_value=11):self.note(10,PADS[0]);self.note(10,PADS[0],0)
        self.assertIsNone(a.model.notes[36][0])
    def test_forward_pads_keep_note_off_after_routing_changes_and_panic(self):
        a=self.a;a.outputs[3]=Mock();self.note(14,PADS[0]);self.note(15,PADS2[7]);self.note(14,PADS[0],0)
        sent=[v.args[0] for v in a.outputs[3].send.call_args_list]
        self.assertEqual([(m.type,m.channel,m.note) for m in sent],[('note_on',13,PADS[0]),('note_on',14,PADS2[7]),('note_off',13,PADS[0])])
        a.release_forwarded();self.assertEqual(a.outputs[3].send.call_args.args[0].type,'note_off');self.assertFalse(a.forwarded)
    def test_numpad_double_clear_is_same_channel_and_restores_on_undo(self):
        a=self.a;a.model.edit(36,0);a.model.set_cell(0,1,40,0,(80,150))
        with patch('app.time.monotonic',return_value=10):a.action('delete_channel_0')
        self.assertIsNone(a.model.notes[36][0]);self.assertIsNotNone(a.model.patterns[0][1][40][0])
        with patch('app.time.monotonic',return_value=10.2):a.action('delete_channel_0')
        self.assertIsNone(a.model.patterns[0][1][40][0]);a.action('undo');a.action('undo')
        self.assertIsNotNone(a.model.notes[36][0]);self.assertIsNotNone(a.model.patterns[0][1][40][0])
        with patch('app.time.monotonic',return_value=20):a.action('delete_channel_0')
        with patch('app.time.monotonic',return_value=20.1):a.action('delete_channel_2')
        self.assertIsNotNone(a.model.patterns[0][1][40][0])
    def test_pattern_key_double_tap_and_follow_keys_switch(self):
        a=self.a
        with patch('app.time.monotonic',return_value=10):a.action('pattern_2')
        a.clock.switch_pattern.assert_called_with(2,False)
        with patch('app.time.monotonic',return_value=10.2):a.action('pattern_2')
        a.clock.switch_pattern.assert_called_with(2,True)
        a.action('follow_keys');a.audition=True;self.note(8,100)
        self.assertEqual((a.model.channel,a.model.selected,a.model.base),(0,36,36));a.clock.audition_on.assert_called_with(7,100,100)
    def test_mute_drag_fills_skipped_channels_as_one_undo(self):
        a=self.a;a.clock=manual_clock(a.model,[]);a.mute_stroke=None;a.mute_canvas=SimpleNamespace(winfo_width=lambda:900)
        a.mute_drag(SimpleNamespace(x=20),True);a.mute_drag(SimpleNamespace(x=899),True);a.end_mute()
        self.assertTrue(all(a.model.muted));a.action('undo');self.assertFalse(any(a.model.muted))
        a.clock.close()
    def test_settings_round_trip_defaults_and_readable_numpad_keys(self):
        config=normalize_settings(json.loads(json.dumps(DEFAULT)));self.assertEqual(config,DEFAULT)
        self.assertEqual(pretty_key('ALT+VK_69'),'Alt + Num 9')
        self.assertEqual(key_id(SimpleNamespace(keycode=0x61,state=4),'win32'),'CTRL+VK_61')
        bad=copy.deepcopy(config);bad['bindings'][1][1]='VK_20'
        with self.assertRaises(ValueError):normalize_settings(bad)
        bad=copy.deepcopy(config);bad['theme']['bank2']['16'][4]='red'
        with self.assertRaises(ValueError):normalize_settings(bad)

if __name__=='__main__':unittest.main()
