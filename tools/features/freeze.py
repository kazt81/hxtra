"""Freeze: the Hold Sustain block (Pitch/Synth > Mono), which, turned on, grabs the sound just before and plays it on as 32
steady sines (tools/patch_freeze.py, after the Metronome and before the tools that add knobs).
A checkbox in the web page's DSP features (WEB 'dsp': its kernel takes Block 3 and Entry 2 room, tools/block3.py) and HX_FREEZE
for build.py. It fits only beside 1 NAM slot or none, so the page leaves it unticked and lists it last (ORDER).

On the M4 side, besides the model's tables and its name in the lists of models that load off (tools/patch_freeze.py), a preset
saved with the block on loads it off (src/m4/freeze.s): the preset load would otherwise turn it on before it has any input, so
that it grabs silence while its footswitch is lit. Each footswitch node keeps its light with its own block, as the stock press
does, so a footswitch that also turns other blocks on comes up with them out of step with Hold Sustain."""
FLAG = 'HX_FREEZE'
WEB = 'dsp'
ORDER = 200
MODULE = 'src/m4/freeze.s'
PRESET_ID = 380                     # fixed for ever: presets store it (tools/patch_freeze.py takes it from here)

APPLY_SITE, APPLY_RECORD = 0x28e0e7d4, 0x28e0cc80   # a preset load applying each block record (0x28e0e5d0)
FS_ADD_SITE, LIST_ADD = 0x28dddb18, 0x28db9cc4      # its footswitch section putting each node it loaded in its list (0x28ddd720)


def apply(p):
    m = p.module(MODULE, inc={'freeze.inc': f'.equ FREEZE_ID, {PRESET_ID}\n'})
    p.chain_bl(APPLY_SITE, APPLY_RECORD, before=m['freeze_rec_off'])
    p.chain_bl(FS_ADD_SITE, LIST_ADD, before=m['freeze_fs_unlit'])
