"""Headless UI state; the actual event handlers remain under test."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock,patch
from app import App,DEFAULT
from core import Model,Pickup,Clock,ScaleTakeover
from editor import Editor
from note_input import NoteInput
from gestures import GridGestures
from pitch_controls import PitchControls

def headless_app():
    a=App.__new__(App);a.model=Model();a.editor=Editor(a.model);a.config=copy.deepcopy(DEFAULT)
    a.pitch_controls=PitchControls(a);a.editor.pitch=a.pitch_controls
    a.scaler=ScaleTakeover();a.select_mode=False;a.note_input=NoteInput(a);a.gestures=GridGestures(a);a.fader_raw={}
    a.stroke=None;a.pickup=Pickup();a.pad_held=set();a.held_actions=set();a.step_holds={};a.undo_hold=None
    a.pad_mode=10;a.group=0;a.encoder_attribute=None;a.knob_mode='By bank';a.scale_factor={}
    a.settings=None;a.audition=False;a.follow_keys=True;a.follow_playhead=False;a.drone_mode=False;a.paint_mode=None
    a.last_tap=None;a.last_midi='';a.error='';a.forward_map={};a.forwarded=set();a.outputs=[None]*4
    a.preview_var=Mock(get=lambda:False);a.clock=Mock();a.gate_until=0
    a.vars={n:Mock() for n in ('velocity','length','bpm','swing')}
    a.canvas=SimpleNamespace(winfo_width=lambda:880,winfo_height=lambda:350,focus_set=lambda:None)
    return a

def manual_clock(model,events):
    with patch('core.threading.Thread'):
        return Clock(model,lambda kind,**kw:events.append((kind,kw)))
