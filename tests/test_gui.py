"""Real Tk event dispatch: exercise focus on buttons, before Tk class bindings."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import app
import mido
from ui_helpers import theme

@unittest.skipUnless(sys.platform=='win32' or os.environ.get('DISPLAY'),'Requires a graphical session')
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.config=patch.object(app,'CONFIG',Path(self.temp.name)/'settings.json');self.config.start()
        self.inputs=patch.object(app.mido,'get_input_names',return_value=[]);self.inputs.start()
        self.outputs=patch.object(app.mido,'get_output_names',return_value=[]);self.outputs.start()
        self.a=app.App(run=False);self.a.root.update()
    def tearDown(self):
        self.a.close();self.inputs.stop();self.outputs.stop();self.config.stop();self.temp.cleanup()
    def test_space_on_options_button_does_not_open_menu(self):
        def children(w):
            for child in w.winfo_children():yield child;yield from children(child)
        button=next(w for w in children(self.a.root) if isinstance(w,ttk.Button) and w.cget('text')=='Options')
        button.focus_force();self.a.root.update()
        button.event_generate('<KeyPress>',keysym='space');self.a.root.update()
        self.assertTrue(self.a.clock.running);self.assertIsNone(self.a.options_window)
        button.event_generate('<KeyPress>',keysym='space');self.a.root.update()
        self.assertTrue(self.a.clock.running)
        button.event_generate('<KeyRelease>',keysym='space');self.a.root.update()
        button.event_generate('<KeyPress>',keysym='space');self.a.root.update()
        self.assertFalse(self.a.clock.running);self.assertEqual(self.a.clock.tick,0);self.assertIsNone(self.a.options_window)
    def test_options_interface_and_shortcut(self):
        self.a.canvas.focus_force();self.a.root.update()
        self.a.canvas.event_generate('<KeyPress>',keycode=191 if sys.platform=='win32' else 61,state=4)
        self.a.root.update();self.assertIsNotNone(self.a.options_window)
        book=next(w for w in self.a.options_window.winfo_children() if isinstance(w,ttk.Notebook))
        self.assertIn('Interface',[book.tab(t,'text') for t in book.tabs()])
    def test_navigation_duplication_and_length_entry(self):
        a=self.a;a.canvas.focus_force();a.root.update()
        def press(win_code,linux_code,state=0):
            code=win_code if sys.platform=='win32' else linux_code
            a.canvas.event_generate('<KeyPress>',keycode=code,state=state);a.root.update()
            a.canvas.event_generate('<KeyRelease>',keycode=code,state=state);a.root.update()
        a.model.edit(36,0)
        press(0x31,10,4);self.assertIsNotNone(a.model.notes[36][1])
        press(0x4C,46,1);self.assertIn((36,2),a.editor.selection)
        alt=0x20000 if sys.platform=='win32' else 8
        press(0x71,68,alt);press(0x36,15,alt);self.assertEqual(a.model.lengths[0],26)
        press(0x76,73,alt);press(0x38,17,alt);self.assertEqual(a.model.lengths[0],8)
        press(0x75,72,alt);press(0x39,18,alt);self.assertEqual(a.model.lengths[0],8)
    def test_shift_mouse_selection_and_gate_display(self):
        a=self.a;a.model.edit(36,0);a.canvas.focus_force();a.root.update()
        h=a.canvas.winfo_height()
        a.canvas.event_generate('<ButtonPress-1>',x=81,y=h-2,state=1)
        a.canvas.event_generate('<Motion>',x=180,y=h-40,state=257)
        a.canvas.event_generate('<ButtonRelease-1>',x=180,y=h-40,state=1)
        a.root.update();self.assertGreater(len(a.editor.selection),1)
        a.set_gate(True);a.draw()
        self.assertIn('100%',[a.canvas.itemcget(i,'text') for i in a.canvas.find_all() if a.canvas.type(i)=='text'])
    def test_numpad_mute_clear_double_clear_and_undo(self):
        a=self.a;a.canvas.focus_force();a.root.update()
        a.model.edit(36,0);a.model.set_cell(0,1,40,0,(70,200))
        code=0x61 if sys.platform=='win32' else 87
        def press(state):
            a.canvas.event_generate('<KeyPress>',keycode=code,state=state);a.root.update()
            a.canvas.event_generate('<KeyRelease>',keycode=code,state=state);a.root.update()
        press(0x20000 if sys.platform=='win32' else 8);self.assertTrue(a.model.muted[0])
        press(4);self.assertIsNone(a.model.notes[36][0]);self.assertIsNotNone(a.model.patterns[0][1][40][0])
        press(4);self.assertIsNone(a.model.patterns[0][1][40][0])
        a.action('undo');self.assertIsNotNone(a.model.patterns[0][1][40][0])
        a.action('undo');self.assertIsNotNone(a.model.notes[36][0])
    def test_midi_learn_gate_knob_and_settings_round_trip(self):
        a=self.a;a.model.edit(36,0);a.options();d=a.settings;d.book.select(1);a.root.update()
        index=next(i for i,r in enumerate(d.rows) if r[0]=='knob_gate_0')
        d.tree.selection_set(str(index));d.select_row();d.start_learn()
        a.midi(2,mido.Message('control_change',channel=3,control=22,value=39))
        self.assertIsNone(d.learn);self.assertEqual(d.rows[index][2:],[2,4,'control_change',22])
        self.assertEqual(a.model.notes[36][0],(100,100))
        d.apply();self.assertTrue(app.CONFIG.exists());d.close()
        a.midi(2,mido.Message('control_change',channel=3,control=22,value=39))
        self.assertGreater(a.model.notes[36][0][1],100);self.assertEqual(a.model.notes[36][0][0],100)
        a.options();self.assertEqual(a.settings.book.index('current'),1)
        for appearance in ('Light','Dark','Legacy light'):
            a.settings.appearance.set(appearance);a.settings.apply();a.draw();a.root.update()
            self.assertEqual(a.config['theme']['ui'],appearance)
    def test_bound_pc_forward_pad_releases_and_modifier_capture(self):
        from unittest.mock import Mock
        a=self.a;a.outputs[3]=Mock();row=next(r for r in a.config['bindings'] if r[0]=='pad_14_0');row[1]='VK_54'
        a.canvas.focus_force();a.root.update()
        a.canvas.event_generate('<KeyPress>',keysym='t');a.root.update()
        a.canvas.event_generate('<KeyRelease>',keysym='t');a.root.update()
        self.assertEqual([c.args[0].type for c in a.outputs[3].send.call_args_list],['note_on','note_off'])
