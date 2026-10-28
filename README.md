# MeetStep — Windows x64 standalone prototype

Python 3.12 + Tk + RtMidi. No DAW or plugin host required. The app sends MIDI;
it does not synthesize audio. For a local software instrument, install/configure
a virtual MIDI cable separately and select its receiving route in the instrument.

## Run / build on Windows

With Python 3.12 x64 installed, run `powershell -File build-windows.ps1`.
This script has not been executed on Windows yet.


```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller==6.11.1
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python app.py
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name MeetStep --add-data "led_packets.json;." --hidden-import mido.backends.rtmidi app.py
```

Result: `dist/MeetStep.exe`, bundles Python and dependencies. GitHub Actions also
builds this executable on Windows x64. Workflow has not yet been run.

## MIDI setup

Options → MIDI: choose SMK input, optional controller 2, notes/clock output and
SMK RGB output. Apply activates and saves; Close discards unapplied edits.
Output channel defaults to 10. Port selections and shortcuts persist in
`~/.meetstep.json`. Choose separate output ports; do not loop the output into input.

Default bindings: channel 10 note 52 = play/stop; channel 6 CC48 = velocity,
CC49 = length, CC55 = BPM. These are the first knob bank.
Change numbers to 56/57/63 for the second bank. Existing saved custom bindings are retained. PC Space toggles play/pause; resume emits MIDI Continue from the preserved position.
The Stop button resets position; pad 52 still toggles play/stop. Holding Space does not repeat.
Controller 0 in a binding disables its MIDI assignment.
Shortcut rows accept PC Tk keysyms, controller 1/2, channels 1–16,
`note_on` or `control_change`, number 0–127. Absolute CC mode only.

Channels 1–9 from SMK select notes; channel 10 pads use the supplied physical
order. Note-off and zero-velocity note-on are ignored. Default selection 36 = C1.
Left click sets a step, right click erases; hold either button and drag to fill or erase
the starting note only. Fast movement fills skipped steps; vertical motion never edits
adjacent notes. Release ends the stroke. Changing the range, selecting a note via MIDI,
losing focus or opening Options cancels it. Pad presses toggle. New steps capture
current velocity and gate length (15–300% of a sixteenth). Knobs change insertion
parameters. Sixteenth steps run at 30–300 BPM with 24 PPQN clock. Overlapping
repeated pitches are ended before retriggering. Stop releases active notes.
JSON save/load stores all 128×16 steps. One pattern is implemented.

## Validation and limitations

Core and mouse-handler tests passed on Linux. Windows binary, GUI rendering and real MIDI
hardware timing have NOT been validated in this environment. Tk is installed,
but there is no graphical display/Xvfb. No Windows EXE is included yet.

RGB packets are extracted verbatim from the supplied USB MIDI capture: 32 red,
then 32 white. USB CIN bytes are removed; MIDI payload/checksum bytes unchanged.
Only these two colors are supported. Packet index is provisionally treated as
physical pad index; this MUST be checked against the hardware. Active steps use
white, inactive red; utility play pad uses white while playing. Other utilities
and individually distinct utility colors are not implemented. No arbitrary RGB
or undocumented checksum algorithm is claimed. LED updates are throttled to one
message per 20 ms, and errors appear in status. Capture ACK parsing is not implemented.

The second output can be selected/opened but has no script engine or routed
messages yet. Hardware MIDI learn, six pattern banks, undo and
script behavior are future work. 

The attached document describes an older project and refers to absent files;
those statements are reference material, not evidence of implemented features.
