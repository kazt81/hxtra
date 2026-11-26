#!/usr/bin/env python3
"""patch_sidechain.py - Input Sidechain on the Noise Gate block (issue #131): its gate keyed by the input, not by its own signal.

usage: patch_sidechain.py <in .hxf | L6IA> <out .hxf | L6IA> [--donor stock.hxf]

The Noise Gate (mono and stereo) gets one knob after its own, Input Sidechain (Off by default). On, its gate opens and closes on
what the Input block's gate hears (the input, L and R summed) while it still gates the signal reaching it, so a gate after drive
follows the clean guitar. src/sharc/gate_sc.asm wraps the Noise Gate's gate core, primitive 0x2720, the Input block's jack
reader, primitive 0x2a94, and the meter, primitive 0x2390: the jack reader arms the next two meters, the Input block's on L and
R ahead of its gate, which capture the key whether Input Gate is on or off. Blobs write no deeper than one level (17,132 stock
writers), so nothing inside the Input block can be marked by a writer:
  Entry 2: gate_sc.asm in Block 3 where tools/block3.py places it (dsp_place), 0x2720's process and control functions and
           the process functions of 0x2a94 and 0x2390 entering it.
  Entry 4: each Noise Gate blob gets the knob's input node, a root default and a writer to each of its cores as pid SC_PID.
  Entry 3: the knob's parameter and state records, copied from the Input block's noiseGate (a bool) with names of its own.
  Entry 0: each Noise Gate's UI Model Info Table row counts the knob, and its Static Model Table cost rises by SC_COST a core.
Run it after tools/patch_gate.py (both rebuild Entry 3's string section) and before tools/patch_comp.py.
"""
import argparse
import os
import struct

import block3
import patch_amp as pa
import patch_comp as pc
import patch_gate as pg
import nam_multi

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'sharc', 'gate_sc.asm')
CORE, ORIG, ORIG_CTRL = 0x2720, 0x8e8f2, 0x614b8b      # the gate core, its stock process code and control function
JACK, JACK_ORIG = 0x2a94, 0x8cdbb   # the jack reader, only in the Input block, and its stock process code
METER, METER_ORIG = 0x2390, 0x8da6a     # the meter, the Input block's on L and R after its jack readers, and its process code
SC_PID = 100                        # gate_sc.asm's: Input Sidechain
MODELS = ('HD2_GateNoiseGateMono', 'HD2_GateNoiseGateStereo')
INPUT_MODEL = pg.INPUT_MODEL
KNOB = 'InputSidechain'
META = {'false': 'Off', 'true': 'On', 'displayName': 'Input Sidechain', 'displayNameShort': 'Input SC'}
SC_COST = 10                        # a core: ~100 cycles a 16-sample block [hypothesis: not measured]


def dsp_asm(dm, pm):
    """gate_sc.asm with its data at dm and its code at pm."""
    return open(ASM).read().replace('SC_DM_BASE', f'{dm:#x}').replace('SC_PM_BASE', f'{pm:#x}')


def dsp_size():
    """(data words, instructions) of gate_sc.asm."""
    secs, _ = pa.sasm.assemble(dsp_asm(nam_multi.B3, nam_multi.NW3), 'gate_sc.asm')
    return tuple(sum(len(s.words) for s in secs if s.kind == k) for k in ('dm', 'pm'))


def e2_size():
    """The bytes patch_dsp adds to Entry 2: gate_sc.asm and the core's, the jack reader's and the meter's primitive records."""
    secs, _ = pa.sasm.assemble(dsp_asm(nam_multi.B3, nam_multi.NW3), 'gate_sc.asm')
    return pa.ldr_size(secs, records=3)


def dsp_place():
    """(DM base, PM base) of gate_sc.asm (tools/block3.py)."""
    return block3.place('HX_GATE_SC')


def patch_dsp(l6ia_bytes, log=print):
    """Entry 2: gate_sc.asm at dsp_place(), and the core's process and control functions and the jack reader's process entering it."""
    dm, pm = dsp_place()
    secs, syms = pa.sasm.assemble(dsp_asm(dm, pm), 'gate_sc.asm')
    entries = pa.l6ia.parse(l6ia_bytes)
    e2 = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    ldr = []
    for sec in secs:
        ldr += (pa.pack_init_l48 if sec.kind == 'pm' else pa.pack_init_l32)(sec.addr, sec.words)
        log(f"[+] Entry 2: sidechain {len(sec.words)} {'instructions' if sec.kind == 'pm' else 'words'} @ {sec.kind.upper()} {sec.addr:#x}")
    ldr += pa.wrap_primitive(e2, f'{CORE:#x}:{ORIG:#x}', syms['ENTRY_2720'], (ORIG_CTRL, syms['CTRL_2720']))
    ldr += pa.wrap_primitive(e2, f'{JACK:#x}:{JACK_ORIG:#x}', syms['ENTRY_2A94'])
    ldr += pa.wrap_primitive(e2, f'{METER:#x}:{METER_ORIG:#x}', syms['ENTRY_2390'])
    new, _, _ = pa.l6ia.rebuild_archive(l6ia_bytes, {2: pa.l6ia.swap32(pa.inject_sharc_ldr_blocks(e2, ldr))})
    return new


def core_slots(b0, comp):
    """The node-tree slots of the composite's gate cores."""
    members = pa.entry4_blob.parse_composite(b0, comp)['members']
    return [k + 1 for k, m in enumerate(members) if m['type_id'] == CORE]


def knob_record(info):
    """The knob as patch_gate.e3_add_gate takes it: the Input block's noiseGate record with META for its names."""
    src = next(p for p in pa.find_model(info, INPUT_MODEL)['params'] if p['name'] == 'noiseGate')
    return KNOB, None, dict(src, meta=dict(META))


def patch_sidechain(l6ia_bytes, models=MODELS, log=print):
    e0 = pa.get_entry_swapped(l6ia_bytes, 0)
    e3 = pa.get_entry_swapped(l6ia_bytes, 3)
    e4 = pa.get_entry_swapped(l6ia_bytes, 4)
    before, before_e3 = pa.parse_entry3_full(e3), e3
    knob = knob_record(before)
    e3, S = pc.e3_add_strings(e3, [KNOB, KNOB + 'State'] + [s for kv in META.items() for s in kv])
    assert pc.models_view(before) == pc.models_view(pa.parse_entry3_full(e3)), 'the string section move changed a model'
    assert pc.slot_lists(before_e3) == pc.slot_lists(e3), 'the string section move changed a slot list'
    default = [(KNOB, None, knob[2]['default'], knob[2]['type'])]
    b0 = pa.entry4_blob.blob(struct.unpack('<%dI' % (len(e4) // 4), e4), 0)
    for name in models:
        m = pa.find_model(pa.parse_entry3_full(e3), name)
        b = pa.entry4_blob.blob(struct.unpack('<%dI' % (len(e4) // 4), e4), m['blob_index'])
        cores = core_slots(b0, pa.entry4_blob.top_type(b))
        e3, first, old = pg.e3_add_gate(e3, name, S, [knob])
        e4 = pc.e4_replace_blob(e4, m['blob_index'], pg.blob_add_gate(b, first, cores, default, pid=SC_PID))
        e0 = pc.e0_set_param_counts(e0, m['words'][2], old, old + 1)
        e0, cost = pg.e0_add_cost(e0, m['words'][2], SC_COST * len(cores))
        chk = pa.parse_entry3_full(e3)['models'][m['idx']]
        assert [p['slot'] for p in chk['params']] == list(range(1, old + 2))
        assert not pa.pmap_slots_without_param(e4, m['blob_index'], chk['params'])
        log(f"[+] {name}: Input Sidechain on slot {first} to {len(cores)} core(s), DSP cost {cost} -> {cost + SC_COST * len(cores)}")
    new, _, _ = pa.l6ia.rebuild_archive(l6ia_bytes, {0: e0, 3: e3, 4: e4})
    return new


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', help='.hxf or L6IA')
    ap.add_argument('output')
    ap.add_argument('--donor', help='Stock .hxf of the unit, when input is a raw L6IA and output a .hxf')
    a = ap.parse_args()
    data, is_hxf = pa.load_l6ia_from_any(a.input)
    pa.save_l6ia_to_any(patch_sidechain(patch_dsp(data)), a.output, donor_hxf=a.input if is_hxf else a.donor)
    print(f'[+] Wrote {a.output}')


if __name__ == '__main__':
    main()
