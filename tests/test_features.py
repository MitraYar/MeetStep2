import json
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import mido
from app import App, DEFAULT
from core import Model, Clock, Pickup, PADS, PADS2
from editor import Editor
from lighting import packet, colors, default_theme, blend
from shortcuts import key_id, migrate_bindings

class Features(unittest.TestCase):
    def test_rgb_all_capture_commands_and_black(self):
        capture=json.loads(pathlib.Path('led_packets.json').read_text())
        for i,expected in enumerate(capture):self.assertEqual(packet(i%32,'#ff0000' if i<32 else '#ffffff'),expected)
        for color in ('#000000','#245abc','#00ff00','#0000ff'):
            data=packet(31,color)
            raw=sum(b<<(7*i) for i,b in enumerate(data[9:-1])).to_bytes(13,'little')[:12]
            self.assertEqual(raw[7:10].hex(),color[1:]);self.assertEqual(sum(raw)%256,250)
            self.assertTrue(all(b<128 for b in data[1:-1]))
    def test_palette_cycle_gradient_and_banks(self):
        m=Model();t=default_theme()
        self.assertEqual(colors(m,t,10)[:16],['#000000']*16)
        t['empty_length']=3;t['empty'][:3]=['#ff0000','#00ff00','#0000ff']
        self.assertEqual(colors(m,t,10)[3:6],t['empty'][:3])
        m.velocity=127;m.edit(36,0)
        self.assertEqual(colors(m,t,10)[0],t['high'])
        self.assertEqual(blend(t['low'],t['high'],0),t['low'])
        self.assertEqual(colors(m,t,11)[0:3],colors(m,t,11)[3:6])
        self.assertEqual(colors(m,t,13)[:16],[t['encoder_top']]*8+[t['encoder_bottom']]*8)
        t['bank2']['11'][15]='#123456';self.assertEqual(colors(m,t,11)[31],'#123456')
    def test_copy_clear_and_undo_are_isolated(self):
        m=Model();m.channel=4;m.edit(36,63);m.edit(37,0);m.select(36)
        m.copy_to(3,True)
        self.assertEqual(m.patterns[3][4][36][63],(100,100));self.assertIsNone(m.patterns[3][4][37][0])
        m.copy_to(2);self.assertEqual(m.patterns[2][4][37][0],(100,100))
        m.history();self.assertIsNone(m.patterns[2][4][37][0])
        m.history(True);self.assertEqual(m.patterns[2][4][37][0],(100,100))
        m.clear('channel');self.assertFalse(any(v for r in m.notes for v in r))
        m.history();self.assertIsNotNone(m.notes[36][63])
        self.assertIsNone(m.patterns[2][0][37][0])
    def test_save_load_and_legacy_import(self):
        m=Model();m.channel=8;m.pattern=7;m.edit(127,63)
        restored=Model();restored.load(json.loads(json.dumps(m.dump())))
        self.assertEqual(restored.patterns[7][8][127][63],(100,100))
        old=[[None]*16 for _ in range(128)];old[36][15]=[77,300];restored.load(old)
        self.assertEqual(restored.notes[36][15],(77,300));self.assertEqual(len(restored.notes[36]),64)
        before=restored.dump();bad={'version':2,'patterns':[],'bpm':120}
        with self.assertRaises(ValueError):restored.load(bad)
        self.assertEqual(before,restored.dump())
    def test_pickup_crossing_change_and_bounded_catch(self):
        p=Pickup();self.assertIsNone(p.value('a',0,100,1,127))
        self.assertIsNone(p.value('a',40,100,1,127))
        v=p.value('a',127,100,1,127);self.assertLessEqual(v,108)
        self.assertIsNone(p.value('a',127,50,1,127))
        p.reset();self.assertIsNone(p.value('a',127,100,1,127))
    def test_physical_keys_independent_of_text(self):
        for text in ('slash','period','.'):
            self.assertEqual(key_id(SimpleNamespace(keycode=191,state=4,keysym=text),'win32'),'CTRL+VK_BF')
        migrated=migrate_bindings({'bindings':[['play','space',1,10,'note_on',52]]})
        self.assertEqual(next(r[1] for r in migrated if r[0]=='pause'),'VK_20')

class Routing(unittest.TestCase):
    def setUp(self):
        a=App.__new__(App);self.a=a;a.model=Model();a.stroke=None;a.pickup=Pickup()
        a.config=DEFAULT;a.pad_held=set();a.pad_mode=10;a.group=0;a.encoder_attribute=None
        a.clock=Mock();a.preview_var=SimpleNamespace(get=lambda:False)
        a.editor=Editor(a.model);a.scale_factor={};a.undo_hold=None;a.audition=False;a.knob_mode='By bank'
        a.vars={name:Mock() for name in ('velocity','length','bpm')}
    def note(self,ch,n,on=True,zero=False):
        self.a.midi(1,mido.Message('note_on' if on else 'note_off',channel=ch-1,note=n,velocity=0 if zero else 100))
    def test_preview_and_both_copy_modifiers(self):
        a=self.a;a.model.edit(36,0)
        self.note(11,PADS[8]);self.note(11,PADS[3])
        self.assertEqual(a.model.pattern,3);a.clock.switch_pattern.assert_not_called()
        self.note(11,PADS[8],zero=True);self.note(11,PADS[0]);a.clock.switch_pattern.assert_called_with(0)
        self.note(11,PADS[9]);self.note(11,PADS[5]);self.assertIsNotNone(a.model.patterns[5][0][36][0])
        self.note(11,PADS[9],False);self.note(11,PADS[10]);self.note(11,PADS[7])
        self.assertIsNotNone(a.model.patterns[7][0][36][0]);self.assertEqual(a.model.pattern,0)
    def test_channels_steps_and_encoder_groups(self):
        a=self.a;self.note(9,60);self.assertEqual(a.model.channel,8)
        a.select_group(7);self.assertEqual((a.group,a.model.page),(7,3))
        self.note(10,PADS[15]);self.assertIsNotNone(a.model.notes[60][63])
        a.midi(1,mido.Message('control_change',channel=5,control=63,value=0))
        self.assertEqual(a.model.notes[60][63][1],100)
        a.midi(1,mido.Message('control_change',channel=5,control=63,value=127))
        self.assertGreater(a.model.notes[60][63][1],100)
        self.assertEqual(a.model.bpm,120)
    def test_utility_pads(self):
        for ch in (10,11):
            self.note(ch,PADS2[8]);self.a.clock.pause_toggle.assert_called()
            self.a.model.edit(36,0,True);self.note(ch,PADS2[15]);self.note(ch,PADS2[15],False);self.assertIsNone(self.a.model.notes[36][0])
            if ch==10:self.note(ch,PADS2[7]);self.assertIsNotNone(self.a.model.notes[36][0])
        before=self.a.group;self.note(13,PADS2[7]);self.assertEqual(self.a.group,before)

class Playback(unittest.TestCase):
    def test_all_channels_64_steps_and_view_does_not_play(self):
        m=Model();m.set_cell(0,0,36,63,(80,100));m.set_cell(0,8,36,63,(90,100));m.set_cell(1,0,70,63,(100,100))
        m.pattern=1
        events=[];c=Clock(m,lambda typ,**kw:events.append((typ,kw)))
        try:
            with c.lock:
                c.running=True;c.tick=63*6;c.next=100;c.advance(100)
                notes=[kw for typ,kw in events if typ=='note_on']
                self.assertEqual({v['channel'] for v in notes},{0,8});self.assertTrue(all(v['note']==36 for v in notes))
                c.tick=64*6;c.next=101;c.advance(101);self.assertEqual(c.step,0)
                c.switch_pattern(1);self.assertFalse(c.active);self.assertEqual(m.playing,1)
        finally:c.close()
