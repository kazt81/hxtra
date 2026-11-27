#!/usr/bin/env python3
"""patch_freeze.py - the Hold Sustain block: turned on, it grabs the sound before and plays it on as 32 steady sines.

usage: patch_freeze.py <in .hxf | L6IA> <out .hxf | L6IA> [--donor stock.hxf]

Run after tools/patch_click.py and before the tools that add knobs (build.py does it for HX_FREEZE=1 builds). It adds:
  - the model Pitch/Synth > Mono > Hold Sustain (Entries 0, 3, 4; preset ID 380): a copy of the mono effect host whose
    one member is the primitive 0x012e, with the knobs Attack, Release, FX Level and Dry Level (pids 5..8) and Hold (pid
    9), hidden, which the block's on/off drives as the stock Feedbacker's Enable: Table 2's followEnable flag and the
    parameter's followEnable meta. Its browser item is Poly Pitch's, block kind 24, so turning the block off does not
    bypass the kernel: it plays the input and the release itself. The instance has the kernel's DM_WORDS of DM and its
    SDR_NEED of SDRAM (the ring), in whole 0x400 words;
  - in the two lists of models that load off (the block loader's and the add-block command's), Hold Sustain's name
    where they compare Infinite Sustain's, which no HX Stomp browser list has: a new block and a loaded preset start off
    and hold nothing;
  - the kernel src/sharc/freeze.asm (Entry 2), in Block 3 where tools/block3.py places it, as the primitive's process
    function. Its data that is all zeros goes in as one zero-fill block, so its sections go through patch_amp's packers,
    not kit.patch_kernel's.
Entry 3's string section then goes back to its stock place (patch_comp.e3_add_strings), so that Entry 3 stays as small
as an amp-loading unit needs.
"""
import argparse
import os
import re
import struct
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sharc'))

import block3
import kit_patch_amp as kit
from features import freeze as feature
import l6ia
import nam_multi
import patch_amp as pa
import patch_comp

FLAG = 'HX_FREEZE'
ASM = os.path.join(SCRIPT_DIR, '..', 'src', 'sharc', 'freeze.asm')
NAME, DISPLAY = 'HD2_PitchHoldSustainMono', 'Hold Sustain'
PRESET_ID = feature.PRESET_ID      # 380 (147 and 148 were an early NAM build's)
DSP_COST = 500                      # 5.0%, until the unit's meter measures it
CLONE = 'L6SPB_PolyPitch'           # Pitch/Synth > Mono, block kind 24: never bypassed, as Feedbacker and Poly Sustain
CATEGORY = 8                        # Pitch/Synth
HOST = 'HD2_VolPanVolMono'
PRIM = (0x012e, 0x200058)           # kit_patch_amp.UNUSED_SHARC_PRIMS' third: NAM and the Metronome have the first two
REGISTRY = (0x611e90, 0, 0x611ef4, 0x611ddd)    # a hooked primitive's init, 0, ? and control function (the generic
#                                     store: pid p into DM(p, I0)), as kit.patch_kernel writes them
LEVEL = [('displayType', 'db'), ('valueMinString', 'Off')]      # -60 dB and under: the kernel's 0
SECONDS = [('displayType', 'time'), ('units', 'sec')]
# (slot, name, pid, type, min, max, default, meta) by display order, Hold last and hidden. Types: 3 float, 1 bool.
PARAMS = ((1, 'Attack', 5, 3, 0.01, 4.0, 0.1, SECONDS),
          (2, 'Release', 6, 3, 0.05, 10.0, 0.5, SECONDS),
          (3, 'FXLevel', 7, 3, -60.0, 6.0, -12.0, [('displayName', 'FX Level'), ('displayNameShort', 'FX Lvl')] + LEVEL),
          (4, 'DryLevel', 8, 3, -60.0, 6.0, 0.0, [('displayName', 'Dry Level'), ('displayNameShort', 'Dry Lvl')] + LEVEL),
          (5, 'Hold', 9, 1, 0, 0, 0, [('false', 'Off'), ('true', 'On'), ('followEnable', 'true')]))
SHOWN = 4                           # Table 2's displayParamCount: Hold is not shown
LOAD_OFF = 0x661                    # Infinite Sustain's name: the entry of the load-off lists Hold Sustain takes


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


def load_off(e0, name_idx):
    """Entry 0 with the two load-off lists comparing name_idx where they compared LOAD_OFF: each a run of
    `movw r2, #name; cmp r3, r2; beq ...`, LOAD_OFF's right after 3 Note Generator Stereo's (0xad5). Returns (new Entry
    0, the two movw addresses)."""
    e0 = bytearray(e0)
    _, poff, slen, dst, _ = kit._parse_e0_segments(e0)[6]
    run = re.compile(re.escape(kit._encode_thumb_movw(2, 0xad5) + b'\x93\x42') + b'.\xd0'
                     + re.escape(kit._encode_thumb_movw(2, LOAD_OFF)), re.S)
    sites = [dst + m.start() + 8 for m in run.finditer(bytes(e0[poff:poff + slen])) if m.start() % 2 == 0]
    if len(sites) != 2:
        raise SystemExit(f'found {len(sites)} load-off lists in Entry 0, not 2')
    for va in sites:
        e0[poff + va - dst:poff + va - dst + 4] = kit._encode_thumb_movw(2, name_idx)
    return bytes(l6ia.fix_internal_crcs(e0)), sites


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
        n_params=len(params), shown=SHOWN, follow_enable=True, fx=True)
    log(f"[+] Entry 0: preset_id {pid}, dsp_cost {cost}, Pitch/Synth > Mono")
    new_e0, sites = load_off(new_e0, m['words'][2])
    log(f"[+] Entry 0: loads off ({', '.join(f'{a:#x}' for a in sites)})")

    entries = l6ia.parse(l6ia_bytes)
    e2_raw = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    e2_raw, _ = kit.expand_sharc_blob0_buffer(e2_raw)
    ldr, entry = kernel_ldr(e2_raw, log)
    e2_raw = pa.inject_sharc_ldr_blocks(e2_raw, ldr)
    out, _, _ = l6ia.rebuild_archive(l6ia_bytes, {0: bytes(new_e0), 2: l6ia.swap32(e2_raw), 3: new_e3, 4: new_e4})
    return out, {'model_id': model_id, 'blob': blob, 'composite': comp, 'preset_id': pid, 'entry': entry,
                 'place': dsp_place(), 'params': params, 'load_off': sites}


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
