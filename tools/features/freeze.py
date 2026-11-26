"""Freeze: the Hold Sustain block (Pitch/Synth), which grabs the sound just before Hold and plays it on as 32 steady sines
(tools/patch_freeze.py, after the Metronome and before the tools that add knobs).
A checkbox in the web page's DSP features (WEB 'dsp': its kernel takes Block 3 and Entry 2 room, tools/block3.py) and HX_FREEZE
for build.py. It fits only beside 1 NAM slot or none, so the page leaves it unticked and lists it last (ORDER).

Nothing on the M4 side: Pitch/Synth is a stock category."""
FLAG = 'HX_FREEZE'
WEB = 'dsp'
ORDER = 200
