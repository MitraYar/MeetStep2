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
