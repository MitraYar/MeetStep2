import unittest
from types import SimpleNamespace
from app import App, DEFAULT
from core import Model, Pickup
from editor import Editor
from unittest.mock import Mock
import mido
from helpers import headless_app

class MouseTests(unittest.TestCase):
    def setUp(self):
        self.app=headless_app()
    def event(self,x,y):return SimpleNamespace(x=x,y=y)
    def test_fill_and_erase_locked_row_in_both_directions(self):
        a=self.app
        a.click(self.event(81,349))
        a.drag(self.event(879,31),1)
        self.assertTrue(all(a.model.notes[36][:16]))
        self.assertFalse(any(a.model.notes[36][16:]))
        self.assertTrue(all(not any(row) for row in a.model.notes[:36]+a.model.notes[37:]))
        a.end_stroke(1)
        a.click(self.event(879,349),False)
        a.drag(self.event(81,-100),3)
        self.assertFalse(any(a.model.notes[36]))
    def test_release_range_and_midi_cancel(self):
        a=self.app
        for cancel in (lambda:a.end_stroke(1),lambda:a.range(16),
                       lambda:a.midi(1,mido.Message('note_on',channel=0,note=90,velocity=100))):
            a.model=Model();a.editor=Editor(a.model);a.stroke=None
            a.click(self.event(81,349));cancel();a.drag(self.event(879,31),1)
            self.assertEqual(sum(bool(c) for r in a.model.notes for c in r),1)
    def test_header_and_second_button_do_not_start_new_row(self):
        a=self.app;a.click(self.event(81,10));self.assertIsNone(a.stroke)
        a.click(self.event(81,349));a.click(self.event(879,31),False)
        a.drag(self.event(879,31),3)
        self.assertEqual(sum(bool(c) for r in a.model.notes for c in r),1)
    def test_fader_defaults(self):
        self.assertEqual([r[-1] for r in DEFAULT['bindings'] if r[0] in ('velocity','length','tempo')],[64,65,67])
