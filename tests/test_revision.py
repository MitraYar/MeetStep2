import copy
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import mido
from core import ScaleTakeover,PADS
from helpers import headless_app,manual_clock
from midi_io import MidiPorts,coalesce_controls

class InputRevision(unittest.TestCase):
    def setUp(self):
        self.a=headless_app();self.events=[];self.a.clock=manual_clock(self.a.model,self.events)
    def tearDown(self):self.a.clock.close()
    def point(self,s=0,n=36):return SimpleNamespace(x=105+s*50,y=340-(n-36)*20,state=0)
    def key(self,n,on=True):self.a.midi(1,mido.Message('note_on' if on else 'note_off',channel=0,note=n,velocity=90))
    def paint(self,s=0,n=36):self.a.click(self.point(s,n));self.a.end_stroke(1)
    def test_pitch_selection_combines_resets_and_preserves_articulation(self):
        a=self.a;m=a.model;m.edit(36,0,articulation='legato');m.edit(40,0);a.editor.selection={(36,0)}
        a.action('pitch_1');a.action('pitch_8');meta=m.notes[36][0][2]
        self.assertEqual((meta['bend'],meta['micro'],meta['mode']),(1,-50,'legato'));self.assertEqual(len(m.notes[40][0]),2)
        a.action('pitch_reset');self.assertEqual(m.notes[36][0][2],{'mode':'legato'})
        a.action('undo');self.assertEqual(m.notes[36][0][2]['micro'],-50)
    def test_held_pitch_repeats_mouse_and_pads_then_releases(self):
        a=self.a;m=a.model;a.action('pitch_1');a.action('pitch_8');a.pitch_controls.held={1,8}
        self.paint();self.paint(1)
        for s in (0,1):self.assertEqual((m.notes[36][s][2]['bend'],m.notes[36][s][2]['micro']),(1,-50))
        a.handle_pad(10,2,True,('pad',2));a.release_step(('pad',2));self.assertEqual(m.notes[36][2][2]['bend'],1)
        a.pitch_controls.release(1);a.pitch_controls.release(8);self.paint(3)
        self.assertEqual(m.notes[36][3],(100,100))
    def test_set_pitch_and_held_reset_paint_existing_only(self):
        a=self.a;m=a.model;m.edit(36,0);m.edit(37,1,articulation='nonlegato')
        a.action('pitch_5');a.action('set_pitch');a.click(self.point());a.drag(self.point(1,37),1);a.end_stroke(1)
        self.assertEqual(m.notes[36][0][2]['micro'],-68);self.assertEqual(m.notes[37][1][2]['mode'],'nonlegato')
        self.paint(3,37);self.assertIsNone(m.notes[37][3])
        a.pitch_controls.reset_held=True;a.click(self.point());a.drag(self.point(1,37),1);a.end_stroke(1)
        self.assertEqual(m.notes[36][0],(100,100));self.assertEqual(m.notes[37][1][2],{'mode':'nonlegato'})
    def test_pending_pitch_mouse_insert_consumes_only_after_new_note(self):
        a=self.a;a.action('pitch_2');a.action('pitch_6');self.paint()
        self.assertEqual(a.model.notes[36][0][2]['bend'],2);self.assertEqual(a.model.notes[36][0][2]['micro'],22)
        self.paint(1);self.assertEqual(a.model.notes[36][1],(100,100))
    def test_cancel_toggles_off_and_legato_does_not_reenable_cancel(self):
        a=self.a;a.action('cancel_articulation');a.action('cancel_articulation');self.assertIsNone(a.editor.articulation)
        self.paint();self.assertIsNone(a.editor.articulation)
        a.action('legato');a.action('legato');self.assertIsNone(a.editor.articulation)
    def test_mono_selected_step_transposes_all_metadata_without_held_pad(self):
        a=self.a;m=a.model;value=(77,43,{'mode':'legato','micro':22,'bend':2,'approach':a.config['pitch']['approach'][1]})
        m.set_cell(0,0,36,2,value);m.mono[0]=True;a.editor.selection={(36,2)}
        self.key(60);self.assertIsNone(m.notes[36][2]);self.assertEqual(m.notes[60][2],value)
        self.assertEqual(a.editor.selection,{(60,2)});self.assertEqual(m.selected,60)
    def test_mono_pad_overwrites_pitch_without_changing_chosen_note(self):
        a=self.a;m=a.model;m.set_cell(0,0,40,0,(71,88,{'mode':'nonlegato','micro':-50}));m.mono[0]=True;m.select(60)
        a.handle_pad(10,0,True,('pad',0));a.release_step(('pad',0))
        self.assertIsNone(m.notes[40][0]);self.assertEqual(m.notes[60][0],(71,88,{'mode':'nonlegato','micro':-50}));self.assertEqual(m.selected,60)
    def test_step_chord_is_held_for_two_minutes_and_note_off_stops_repeating(self):
        a=self.a;a.action('step_input');self.key(60);self.key(64);a.note_input.poll(200)
        self.assertEqual(a.editor.step,0);a.action('grid_right');a.action('grid_right')
        self.assertTrue(all(a.model.notes[n][s] for n in (60,64) for s in range(3)))
        self.key(60,False);a.action('grid_right');self.assertIsNone(a.model.notes[60][3]);self.assertIsNotNone(a.model.notes[64][3])
        self.key(64,False);a.action('grid_right');self.assertFalse(any(r[4] for r in a.model.notes))
    def test_sticky_adds_separate_handfuls_regular_input_replaces_chord(self):
        a=self.a;a.action('step_input');self.key(60);self.key(60,False);self.key(64);self.key(64,False)
        self.assertIsNone(a.model.notes[60][0]);self.assertIsNotNone(a.model.notes[64][0])
        a.action('sticky_input');self.key(67);self.key(67,False);self.key(71)
        self.assertTrue(all(a.model.notes[n][0] for n in (64,67,71)))
    def test_delete_cursor_and_drone_header(self):
        a=self.a;a.model.edit(36,0);a.action('delete_selection');self.assertIsNone(a.model.notes[36][0])
        a.action('undo');a.action('delete_selection_back');self.assertIsNone(a.model.notes[36][0])
        a.action('drone');e=SimpleNamespace(x=40,y=340,state=0);a.click(e);self.assertTrue(a.model.drones[0][0][36])
        a.click(e,False);self.assertFalse(a.model.drones[0][0][36]);self.assertIsNone(a.stroke)
    def test_disable_modifiers_preserves_playback_controls(self):
        a=self.a;a.select_mode=True;a.editor.articulation='gate';a.paint_mode='length';a.drone_mode=True
        a.note_input.step=a.note_input.sticky=a.note_input.record=a.note_input.hotkeys=True
        a.model.mono[0]=True;a.editor.repeat_pages=True;a.audition=True;a.show_gate=True;a.pitch_controls.mode=True
        a.action('disable_modifiers')
        self.assertFalse(any((a.follow_keys,a.follow_playhead,a.select_mode,a.paint_mode,a.drone_mode,a.note_input.step,a.note_input.sticky,a.note_input.record,a.model.mono[0],a.pitch_controls.mode)))
        self.assertIsNone(a.editor.articulation);self.assertTrue(a.editor.repeat_pages and a.audition and a.show_gate and a.note_input.hotkeys)
    def test_visual_shift_crosses_page_without_moving_hardware(self):
        a=self.a;a.action('view_right');self.assertEqual((a.editor.view_start,a.model.page,a.group),(1,0,0))
        self.paint(15);self.assertIsNotNone(a.model.notes[36][16]);self.assertEqual((a.model.page,a.group),(0,0))
        a.handle_pad(10,0,True,('pad',0));a.release_step(('pad',0));self.assertIsNotNone(a.model.notes[36][0])
        for reset in ('left','right','home','end','prev_page','next_page','page_left','page_right'):
            a.editor.view_offset=-1 if a.model.page else 1;a.action(reset);self.assertEqual(a.editor.view_offset,0)
    def test_scaling_64_selected_cells_never_expands_to_other_notes_or_channels(self):
        a=self.a;m=a.model
        for c in (0,1):
            for n in (36,40):
                for s in range(64):m.set_cell(0,c,n,s,(60,100))
        a.editor.selection={(36,s) for s in range(64)};a.editor.scope='all_channels';m.undo_stack.clear()
        a.editor.scale('velocity',.5);a.editor.scale('length',2)
        self.assertTrue(all(cell==(30,200) for cell in m.notes[36]))
        self.assertTrue(all(cell==(60,100) for cell in m.notes[40]+m.patterns[0][1][36]))
        self.assertEqual([len(e['changes']) for e in m.undo_stack],[64,64])
        a.action('undo');self.assertTrue(all(cell==(30,100) for cell in m.notes[36]))
    def test_absolute_fader_on_held_header_batches_a_full_row_as_one_undo(self):
        a=self.a;m=a.model
        for s in range(64):m.set_cell(0,0,36,s,(60,100))
        m.undo_stack.clear();a.editor.selection={(36,s) for s in range(64)};a.stroke={'kind':'header','button':1}
        a.fader('velocity',10);a.fader('length',127);a.end_stroke(1)
        self.assertEqual(len(m.undo_stack),1);self.assertTrue(all(cell==(11,300) for cell in m.notes[36]))
        a.action('undo');self.assertTrue(all(cell==(60,100) for cell in m.notes[36]))

class ScaleRevision(unittest.TestCase):
    def test_proportional_anchor_30_to_value_60_both_directions(self):
        s=ScaleTakeover();s.value('x',30,60,1,127)
        self.assertEqual(s.value('x',15,60,1,127),30)
        self.assertEqual(s.value('x',0,30,1,127),1)
        s.reset();s.value('x',30,60,1,127)
        self.assertEqual(s.value('x',127,60,1,127),127)
    def test_near_endpoint_reserves_ten_cc_counts_and_retains_fractional_motion(self):
        s=ScaleTakeover();s.value('x',125,60,1,127)
        self.assertEqual(s.value('x',126,60,1,127),67)
        self.assertEqual(s.value('x',127,67,1,127),73)
        s.reset();s.value('x',2,100,15,300)
        self.assertEqual(s.value('x',1,100,15,300),92)
        self.assertEqual(s.value('x',0,92,15,300),83)
        s.reset();value=2;s.value('x',0,value,1,127)
        for raw in range(1,128):value=s.value('x',raw,value,1,127)
        self.assertEqual(value,127)
    def test_coalescing_preserves_turn_reversals_notes_and_original_timestamps(self):
        events=[(1,mido.Message('control_change',channel=0,control=64,value=v),i) for i,v in enumerate((30,31,32,33,32,31,30))]
        note=(1,mido.Message('note_on',note=60),20);events+=[note]+events[:2]
        result=coalesce_controls(events,{(1,0,64)})
        self.assertEqual([e[1].value for e in result if e[1].type=='control_change'],[30,33,32,30,30,31])
        self.assertEqual(result[4],note);self.assertEqual(result[1][2],3)

class FakePort:
    def __init__(self,name,callback=None):self.name=name;self.callback=callback;self.closed=False;self.sent=[]
    def close(self):self.closed=True
    def send(self,msg):
        if self.closed:raise OSError('closed')
        self.sent.append(msg)

class MidiRecovery(unittest.TestCase):
    def setUp(self):
        self.now=[0.0];self.events=queue.Queue();self.backend=Mock();self.backend.get_input_names.return_value=['SMK'];self.backend.get_output_names.return_value=['A','B']
        self.backend.open_input.side_effect=lambda name,callback:FakePort(name,callback)
        self.backend.open_output.side_effect=lambda name:FakePort(name)
        with patch('midi_io.threading.Thread'):self.io=MidiPorts(self.events,self.backend,lambda:self.now[0])
        self.config={'ports':['SMK','','A','','',''],'split_outputs':True,'channel_outputs':['','B']+['']*7}
        self.io.configure(self.config);self.io.service()
    def tearDown(self):
        for i in range(2):self.io.close_input(i)
        for name in list(self.io.open_outputs):self.io.close_output(name)
    def test_shared_outputs_open_once_and_clock_only_uses_first_device(self):
        self.assertEqual(self.backend.open_output.call_count,2)
        a=headless_app();a.config.update(self.config);a.midi_ports=self.io;a.outputs=self.io.outputs
        for p in self.io.open_outputs.values():p.sent.clear()
        for kind in ('clock','start','stop'):a.send(kind)
        for kind,kw in [('note_on',{'note':60,'velocity':90}),('note_off',{'note':60}),('pitchwheel',{'pitch':200}),('control_change',{'control':6,'value':2})]:a.send(kind,channel=1,**kw)
        self.assertEqual([m.type for m in self.io.open_outputs['A'].sent],['clock','start','stop'])
        self.assertEqual([m.type for m in self.io.open_outputs['B'].sent],['note_on','note_off','pitchwheel','control_change'])
        # Apply/Close releases notes through the old open routes before replacing ports.
        a.config['split_outputs']=False;a.send('note_off',channel=1,note=60)
        self.assertEqual(self.io.open_outputs['B'].sent[-1].type,'note_off')
        a.send('note_on',channel=8,note=60);self.assertEqual(self.io.open_outputs['A'].sent[-1].channel,8)
    def test_disconnect_reconnect_rejects_late_callbacks(self):
        old=self.io.inputs[0];self.backend.get_input_names.return_value=[];self.io.service();self.assertTrue(old.closed)
        self.backend.get_input_names.return_value=['SMK'];self.io.service();new=self.io.inputs[0]
        old.callback(mido.Message('note_on',note=60));self.assertTrue(self.events.empty())
        new.callback(mido.Message('note_on',note=64));self.assertEqual(self.events.get_nowait()[1].note,64)
    def test_idle_refresh_does_not_restart_outputs_or_interrupt_held_keys(self):
        old=self.io.inputs[0];output=self.io.outputs[0];self.now[0]=121;self.io.busy[0]=True;self.io.service();self.assertIs(self.io.inputs[0],old)
        self.io.busy[0]=False;self.io.service();self.assertTrue(old.closed);self.assertIsNot(self.io.inputs[0],old);self.assertIs(self.io.outputs[0],output)
    def test_failed_output_recovers_independently_of_inputs(self):
        inp=self.io.inputs[0];old=self.io.outputs[0];self.io.fail_output(old);self.io.service()
        self.assertTrue(old.closed);self.assertIsNot(self.io.outputs[0],old);self.assertIs(self.io.inputs[0],inp)
    def test_missing_output_does_not_prevent_input_or_other_output(self):
        self.backend.get_output_names.return_value=['A'];self.io.service()
        self.assertIsNone(self.io.channel_outputs[1]);self.assertIsNotNone(self.io.inputs[0]);self.assertIsNotNone(self.io.outputs[0])
    def test_open_output_exception_keeps_live_input_open(self):
        self.io.close_output('B');inp=self.io.inputs[0];self.backend.open_output.side_effect=OSError('device busy')
        self.io.service();self.assertFalse(inp.closed);self.assertIs(self.io.inputs[0],inp)
    def test_active_sensing_timeout_recovers_even_with_stuck_held_key(self):
        old=self.io.inputs[0];old.callback(mido.Message('active_sensing'));self.io.busy[0]=True;self.now[0]=2;self.io.service();self.assertTrue(old.closed)
    def test_clock_recovers_only_voices_for_reconnected_route(self):
        a=headless_app();events=[];clock=manual_clock(a.model,events)
        try:
            clock.running=True;clock.step=4;clock.active={(0,36),(1,40)};clock.drone_active={(1,48)}
            clock.recover_output({1});self.assertEqual({kw['note'] for kind,kw in events if kind=='note_on'},{40,48})
            self.assertFalse(any(kind in ('songpos','continue') for kind,kw in events))
            events.clear();clock.recover_output({0},True)
            self.assertIn(('songpos',{'pos':4}),events);self.assertIn(('continue',{}),events)
        finally:clock.close()

if __name__=='__main__':unittest.main()
