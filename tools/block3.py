#!/usr/bin/env python3
"""block3.py - the room the DSP features share in Block 3, where each one's code goes in it, and the room they share in Entry 2.

usage: block3.py    (prints the room for each NAM slot count and each feature's cost, in both)

The DSP features' code (the Metronome's kernel, the FX Loop gate, the GR meter's wrapper) all goes in one room of Block 3:
between NAM A2 Lite's slots and its cold code (tools/sharc/nam_multi.py Layout), or, with no NAM, all of Block 3 from B3 to the
cold code's end. place() packs the features that are on from the top of the room down, in FEATURES order: each one's code from
an even 48-bit address, its data right under it, the next feature under a whole instruction pair. So a feature takes cost()
words whatever else is on.

The same code also goes into Entry 2, the DSP's boot stream, as LDR blocks: e2() bytes a feature, whatever else is on and
wherever it is placed, out of e2_room(), what the stock stream and NAM's kernel leave of the partition. A selection fits when
it fits both (fits()): the web setup page checks that with the numbers tools/m4cache.py writes.

HX_NAM_SLOTS: how many NAM blocks play at once, 3, 2, 1 or 0 (no NAM A2 Lite at all); unset, the most that leave room for the
features that are on (HX_GR=1 alone: 2).
"""
import functools
import importlib
import importlib.util
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sharc'))

import nam_multi
import patch_amp

VAR = 'HX_NAM_SLOTS'
SLOTS = (3, 2, 1, 0)
# (switch, the tool whose dsp_size() gives its (data words, instructions)), from the top of the room down
FEATURES = (('HX_CLICK', 'patch_click'), ('HX_FX_GATE', 'patch_gate'), ('HX_GR', 'patch_comp'), ('HX_USB_MONITOR', 'patch_usbmon'),
            ('HX_GATE_SC', 'patch_sidechain'))


def nw(pm):
    """The normal-word address of Block 3's 48-bit address pm (even)."""
    return nam_multi.NW3 + (pm - nam_multi.NW3) * 3 // 2


def pm_at(n):
    """The even 48-bit address at or under normal word n."""
    pm = nam_multi.NW3 + (n - nam_multi.NW3) * 2 // 3
    return pm - (pm & 1)


@functools.lru_cache(maxsize=None)
def size(flag):
    """(data words, instructions) of the feature's DSP code."""
    return importlib.import_module(dict(FEATURES)[flag]).dsp_size()


def cost(flag):
    """The words the feature takes: its code in whole instruction pairs, its data in whole pairs' worth (3 words)."""
    n_dm, n_pm = size(flag)
    return 3 * -(-n_pm // 2) + 3 * -(-n_dm // 3)


def kernel(unit, slots):
    """build.py's kernel command for `slots` NAM slots (none for 0)."""
    spec = importlib.util.spec_from_file_location('hxtra_build', os.path.join(SCRIPT_DIR, '..', 'build.py'))
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    return build.kernel(unit, slots)


@functools.lru_cache(maxsize=None)
def layout(slots):
    """nam_multi's Layout of build.py's HX Stomp kernel with `slots` slots."""
    return nam_multi.layout(kernel('HX_Stomp', slots)[1:])


@functools.lru_cache(maxsize=None)
def room(slots):
    """[lo, hi): the normal words the features may take beside `slots` NAM slots, hi at an even instruction."""
    if slots == 0:
        return nam_multi.B3, nw(pm_at(nam_multi.COLD_END))
    lay = layout(slots)
    return lay.b3_to, lay.cold_nw


def words(slots):
    lo, hi = room(slots)
    return hi - lo


E2_STOCK = 490648           # stock 3.80.0's Entry 2 (tests/test_block3.py checks it on the stock file)


@functools.lru_cache(maxsize=None)
def e2(flag):
    """The bytes the feature adds to Entry 2."""
    return importlib.import_module(dict(FEATURES)[flag]).e2_size()


@functools.lru_cache(maxsize=None)
def nam_e2(slots):
    """The bytes NAM A2 Lite's kernel for `slots` slots and its primitive record add to Entry 2 (none for 0)."""
    if not slots:
        return 0
    with nam_multi.flags(kernel('HX_Stomp', slots)[1:]):
        asm, _ = nam_multi.build(slots)
    return patch_amp.ldr_size(patch_amp.sasm.assemble(asm, 'nam_lite.asm')[0], records=1)


def e2_room(slots):
    """The bytes of Entry 2 the features may take beside `slots` NAM slots."""
    return patch_amp.E2_MAX - E2_STOCK - nam_e2(slots)


def on(env=os.environ):
    return [f for f, _ in FEATURES if env.get(f)]


def fits(slots, flags):
    return sum(cost(f) for f in flags) <= words(slots) and sum(e2(f) for f in flags) <= e2_room(slots)


def slots(env=os.environ):
    """The NAM slot count of the build env describes: HX_NAM_SLOTS, else the most that leave room for the features on."""
    want, raw = on(env), env.get(VAR)
    need, need_e2 = sum(cost(f) for f in want), sum(e2(f) for f in want)
    if raw:
        if raw not in [str(s) for s in SLOTS]:
            raise SystemExit(f'{VAR} is one of {", ".join(map(str, SLOTS))}, not {raw!r}')
        if need > words(int(raw)):
            raise SystemExit(f'{" + ".join(want)} take {need} words of Block 3; {raw} NAM slots leave {words(int(raw))}')
        if need_e2 > e2_room(int(raw)):
            raise SystemExit(f'{" + ".join(want)} take {need_e2} bytes of Entry 2; {raw} NAM slots leave {e2_room(int(raw))}')
        return int(raw)
    for s in SLOTS:
        if fits(s, want):
            return s
    if need > words(0):
        raise SystemExit(f'{" + ".join(want)} take {need} words of Block 3, more than it has ({words(0)})')
    raise SystemExit(f'{" + ".join(want)} take {need_e2} bytes of Entry 2, more than it has ({e2_room(0)})')


def place(flag, env=os.environ):
    """(DM base, PM base) of the feature's DSP code in the build env describes, the feature on whether env has it or not."""
    env = {**env, flag: '1'}
    s = slots(env)
    lo, top = room(s)
    for f, _ in FEATURES:
        if not env.get(f):
            continue
        n_dm, n_pm = size(f)
        pm = pm_at(top) - n_pm - (n_pm & 1)
        dm = nw(pm) - n_dm
        if dm < lo:
            raise SystemExit(f'{f}\'s DSP code ({n_dm} words, {n_pm} instructions) does not fit beside {s} NAM slots: '
                             f'{dm:#x} < {lo:#x}')
        if f == flag:
            return dm, pm
        top = top - cost(f)
    raise KeyError(flag)


def main():
    for s in SLOTS:
        lo, hi = room(s)
        print(f'{s} NAM slot{"s" * (s != 1)}: {hi - lo} words ({lo:#x}..{hi:#x}), {e2_room(s)} bytes of Entry 2')
    for f, _ in FEATURES:
        print(f'{f}: {cost(f)} words ({size(f)[0]} data, {size(f)[1]} instructions), {e2(f)} bytes of Entry 2')


if __name__ == '__main__':
    main()
