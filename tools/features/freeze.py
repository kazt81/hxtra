"""Freeze: the Hold Sustain block (Pitch/Synth > Mono), which, turned on, grabs the sound just before and plays it on as 32
steady sines (tools/patch_freeze.py, after the Metronome and before the tools that add knobs).
A checkbox in the web page's DSP features (WEB 'dsp': its kernel takes Block 3 and Entry 2 room, tools/block3.py) and HX_FREEZE
for build.py. It fits only beside 1 NAM slot or none, so the page leaves it unticked and lists it last (ORDER).

On the M4 side only data and two immediates: the model's tables, and its name in the lists of models that load off."""
FLAG = 'HX_FREEZE'
WEB = 'dsp'
ORDER = 200
