#!/usr/bin/env python3
"""patch_freeze.py - the Hold Sustain block: Hold grabs the sound just before it and plays it on as 32 steady sines.

usage: patch_freeze.py <in .hxf | L6IA> <out .hxf | L6IA> [--donor stock.hxf]

Run after tools/patch_click.py and before the tools that add knobs (build.py does it for HX_FREEZE=1 builds). It adds:
  - the model Pitch/Synth > Hold Sustain > Hold Sustain (Entries 0, 3, 4; preset ID 380): a copy of the mono effect host
    whose one member is the primitive 0x012e, with the knobs Mode, Hold, Attack, Release, FX Level and Dry Level (pids
    5..10); the instance has the kernel's DM_WORDS of DM and its SDR_NEED of SDRAM (the ring), in whole 0x400 words;
  - the kernel src/sharc/freeze.asm (Entry 2), in Block 3 where tools/block3.py places it, as the primitive's process
    function. Its data that is all zeros goes in as one zero-fill block, so its sections go through patch_amp's packers,
    not kit.patch_kernel's.
Entry 3's string section then goes back to its stock place (patch_comp.e3_add_strings), so that Entry 3 stays as small
as an amp-loading unit needs.
"""
import argparse
import os
import struct
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sharc'))

import block3
import kit_patch_amp as kit
import l6ia
import nam_multi
import patch_amp as pa
import patch_comp

FLAG = 'HX_FREEZE'
ASM = os.path.join(SCRIPT_DIR, '..', 'src', 'sharc', 'freeze.asm')
NAME, DISPLAY, FOLDER = 'HD2_PitchHoldSustainMono', 'Hold Sustain', 'Hold Sustain'
PRESET_ID = 380                     # fixed for ever: presets store it (147 and 148 were an early NAM build's)
DSP_COST = 500                      # 5.0%, until the unit's meter measures it
CLONE = 'HD2_PitchSimplePitchMono'  # a mono Pitch/Synth effect: no trails
CATEGORY = BROWSER = 8              # Pitch/Synth, a folder beside its Mono, Stereo and Legacy lists
HOST = 'HD2_VolPanVolMono'
PRIM = (0x012e, 0x200058)           # kit_patch_amp.UNUSED_SHARC_PRIMS' third: NAM and the Metronome have the first two
REGISTRY = (0x611e90, 0, 0x611ef4, 0x611ddd)    # a hooked primitive's init, 0, ? and control function (the generic
#                                     store: pid p into DM(p, I0)), as kit.patch_kernel writes them
LEVEL = [('displayType', 'db'), ('valueMinString', 'Off')]      # -60 dB and under: the kernel's 0
SECONDS = [('displayType', 'time'), ('units', 'sec')]
# (slot, name, pid, type, min, max, default, meta) by display order. Types: 3 float, 2 int, 1 bool.
PARAMS = ((1, 'Mode', 5, 2, 0, 1, 0, [('displayType', 'list'), ('0', 'Momentary'), ('1', 'Latch')]),
          (2, 'Hold', 6, 1, 0, 0, 0, [('false', 'Off'), ('true', 'On')]),
          (3, 'Attack', 7, 3, 0.01, 4.0, 0.3, SECONDS),
          (4, 'Release', 8, 3, 0.05, 10.0, 1.0, SECONDS),
          (5, 'FXLevel', 9, 3, -60.0, 6.0, 0.0, [('displayName', 'FX Level'), ('displayNameShort', 'FX Lvl')] + LEVEL),
          (6, 'DryLevel', 10, 3, -60.0, 6.0, 0.0, [('displayName', 'Dry Level'), ('displayNameShort', 'Dry Lvl')] + LEVEL))


def word(ty, v):
    return kit.f2u(v) if ty == 3 else int(v) & 0xffffffff


def freeze_params():
    """PARAMS as the kit's add_model_entry3 and add_model_entry4 take them (kit.nam_params' form)."""
    out = []
    for slot, name, pid, ty, mn, mx, dflt, meta in PARAMS:
        if not any(k == 'displayName' for k, _ in meta):
            meta = [('displayName', name)] + meta
        raw = [0, 0, 0, ty, slot, word(ty, mn), word(ty, mx), word(ty, dflt)]
        out.append({'slot': slot, 'pid': pid, 'name': name, 'type': ty, 'op': kit.NAM_INPUT_OP[ty], 'raw': raw,
                    'meta': [(k, 7, v) for k, v in meta], 'state': name + 'State', 'default_word': raw[7]})
    return out


def dsp_asm(dm, pm):
    """freeze.asm with its data at dm and its code at pm."""
    return open(ASM).read().replace('FZ_DM_BASE', f'{dm:#x}').replace('FZ_PM_BASE', f'{pm:#x}')


def assembled(dm=nam_multi.B3, pm=nam_multi.NW3):
    return pa.sasm.assemble(dsp_asm(dm, pm), 'freeze.asm')


def dsp_size():
    """(data words, instructions) of freeze.asm."""
    secs, _ = assembled()
    return tuple(sum(len(s.words) for s in secs if s.kind == k) for k in ('dm', 'pm'))


def e2_size():
    """The bytes add_freeze adds to Entry 2: freeze.asm and its primitive record."""
    return pa.ldr_size(assembled()[0], records=1)


def instance():
    """The instance's DM, PM and SDRAM words: the kernel's own DM_WORDS, and its SDR_NEED in whole 0x400 words, as NAM's."""
    _, syms = assembled()
    return {'dm_words': syms['DM_WORDS'], 'pm_words': 0x0d, 'sdram_words': -(-syms['SDR_NEED'] // 0x400) * 0x400}


def dsp_place():
    """(DM base, PM base) of freeze.asm (tools/block3.py)."""
    return block3.place(FLAG)


def kernel_ldr(e2_raw, log=print):
    """The LDR blocks of freeze.asm at dsp_place() and of the primitive's registry record, its process function the
    kernel's CUSTOM_AMP_ENTRY."""
    dm, pm = dsp_place()
    secs, syms = pa.sasm.assemble(dsp_asm(dm, pm), 'freeze.asm')
    ldr = []
    for sec in secs:
        ldr += (pa.pack_init_l48 if sec.kind == 'pm' else pa.pack_init_l32)(sec.addr, sec.words)
        log(f"[+] Entry 2: Hold Sustain {len(sec.words)} {'instructions' if sec.kind == 'pm' else 'words'} "
            f"@ {sec.kind.upper()} {sec.addr:#x}")
    entry = syms['CUSTOM_AMP_ENTRY']
    ldr += pa.pack_init_l32(PRIM[1], [PRIM[0], *REGISTRY, entry, 0x91, 0x0d])
    log(f"[+] Entry 2: primitive {PRIM[0]:#06x} @ {PRIM[1]:#x} -> kernel {entry:#x}")
    return ldr, entry


def add_freeze(l6ia_bytes, log=print):
    """The Hold Sustain model and its kernel. Returns (new l6ia bytes, info dict)."""
    e0 = kit.get_entry_swapped(l6ia_bytes, 0)
    e3 = kit.get_entry_swapped(l6ia_bytes, 3)
    e4 = kit.get_entry_swapped(l6ia_bytes, 4)
    info = kit.parse_entry3_full(e3)
    if any(m['name'] == NAME for m in info['models']):
        raise SystemExit(f'{NAME} is already in this image')
    assert PRIM[0] not in kit.stock_prims_in_use(l6ia_bytes), f'primitive {PRIM[0]:#x} is in use'
    src = kit.find_model(info, CLONE)
    params = freeze_params()

    hm = kit.find_model(info, HOST)
    w4 = struct.unpack('<%dI' % (len(e4) // 4), e4)
    width = kit.FX_HOST_COMPOSITES[kit.entry4_blob.top_type(kit.entry4_blob.blob(w4, hm['blob_index']))]
    assert width == 1
    kit.fx_source_check(e0, src, CATEGORY, width)
    new_e4, blob, comp = kit.add_model_entry4(e4, hm['blob_index'], params, PRIM[0], instance(), fx=True)
    log(f"[+] Entry 4: Hold Sustain blob {blob} on composite {comp:#x} (primitive {PRIM[0]:#06x})")

    new_e3, model_id, _ = kit.add_model_entry3(e3, src, NAME, DISPLAY, blob, params, drop_meta=kit.FX_MODEL_META_DROP)
    m = kit.parse_entry3_full(new_e3)['models'][model_id]
    assert [(p['name'], p['slot'], p['type']) for p in m['params']] == [(p['name'], p['slot'], p['type']) for p in params]
    orphans = kit.pmap_slots_without_param(new_e4, blob, m['params'])
    assert not orphans, orphans
    new_e3, _ = patch_comp.e3_add_strings(new_e3, [], home=True)
    log(f"[+] Entry 3: {NAME} ({DISPLAY}) = model {model_id}, blob {blob}; {len(new_e3):#x} bytes")

    new_e0, pid, cost, _ = kit.add_model_entry0(
        e0, src['words'][2], m['words'][2], DISPLAY, preset_id=PRESET_ID, dsp_cost=DSP_COST,
        n_params=len(params), folder=(BROWSER, FOLDER), fx=True, src_category=CATEGORY)
    log(f"[+] Entry 0: preset_id {pid}, dsp_cost {cost}, Pitch/Synth > {FOLDER}")

    entries = l6ia.parse(l6ia_bytes)
    e2_raw = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    e2_raw, _ = kit.expand_sharc_blob0_buffer(e2_raw)
    ldr, entry = kernel_ldr(e2_raw, log)
    e2_raw = pa.inject_sharc_ldr_blocks(e2_raw, ldr)
    out, _, _ = l6ia.rebuild_archive(l6ia_bytes, {0: bytes(new_e0), 2: l6ia.swap32(e2_raw), 3: new_e3, 4: new_e4})
    return out, {'model_id': model_id, 'blob': blob, 'composite': comp, 'preset_id': pid, 'entry': entry,
                 'place': dsp_place(), 'params': params}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--donor', help='Stock .hxf of the unit, when input is a raw L6IA and output a .hxf')
    args = ap.parse_args()
    l6ia_bytes, is_hxf = kit.load_l6ia_from_any(args.input)
    out, _ = add_freeze(l6ia_bytes)
    kit.save_l6ia_to_any(out, args.output, donor_hxf=args.input if is_hxf else args.donor)
    print(f"[+] Wrote {args.output}")


if __name__ == '__main__':
    main()
