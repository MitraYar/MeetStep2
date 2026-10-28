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
        self.assertTrue(self.a.clock.paused);self.assertIsNone(self.a.options_window)
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
    @unittest.skipUnless(sys.platform=='win32','Native Windows mouse message')
    def test_windows_forward_button_edits_gate(self):
        import ctypes
        from ctypes import wintypes
        a=self.a;a.model.edit(36,0);a.canvas.focus_force();a.root.update()
        user=ctypes.WinDLL('user32');user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        user.SendMessageW.restype=ctypes.c_ssize_t
        y=a.canvas.winfo_height()-2;pos=lambda yy:81|((yy&65535)<<16)
        user.SendMessageW(a.canvas.winfo_id(),0x020B,2<<16,pos(y))
        user.SendMessageW(a.canvas.winfo_id(),0x0200,0x40,pos(y-100))
        user.SendMessageW(a.canvas.winfo_id(),0x020C,2<<16,pos(y-100))
        self.assertGreater(a.model.notes[36][0][1],127);self.assertIsNone(a.side_stroke)
