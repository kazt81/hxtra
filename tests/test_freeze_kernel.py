"""The freeze block's kernel (src/sharc/freeze.asm) in ssim, call by call, against tools/sharc/freeze.py: the registers,
the levels, the decimator and its ring in SDRAM, the first call and the tables made over the first calls."""
import random
import re
from pathlib import Path

import numpy as np
import pytest

import freeze as fz
import sasm
import ssim

ROOT = Path(__file__).resolve().parent.parent
ASM = ROOT / 'src' / 'sharc' / 'freeze.asm'
DM, PM = 0xC0000, 0x8C200
I0, BI, BO, ENTRY, SDRAM = 0xB3000, 0xB8000, 0xB8100, 0xB4000, 0x400000
SDR_WORDS = 0x1400
B = fz.BLOCK


def assemble():
    src = ASM.read_text().replace('FZ_DM_BASE', f'{DM:#x}').replace('FZ_PM_BASE', f'{PM:#x}')
    return sasm.assemble(src, 'freeze.asm')


SECS, SYMS = assemble()


class Kernel:
    """The kernel and one instance, made as the stock makes one: its first 145 words 0 but DM(3) = 1, the rest and its
    SDRAM block stale (random). call() runs one block and checks that no register changed."""

    def __init__(self, effect_db=0.0, dry_db=0.0, tables=True, sdram_words=SDR_WORDS, stale=True, out=BO, seed=1,
                 mode='momentary', attack=0.3, release=1.0):
        self.sim = sim = ssim.Sim()
        sim.strict_cbufen = True
        sim.load(SECS)
        self.rnd = rnd = random.Random(seed)
        self.out = out
        for k in range(145):
            sim.wr(I0 + k, 0)
        sim.wr(I0 + 3, 1)
        for k in range(145, SYMS['DM_WORDS']):
            sim.dm[I0 + k] = rnd.getrandbits(32) if stale else 0
        sim.wr(ENTRY + 2, ENTRY + 0x10)
        sim.wr(ENTRY + 0x10 + 6, SDRAM)
        sim.wr(ENTRY + 0x10 + 7, SDRAM + sdram_words)
        for k in range(SDR_WORDS):
            sim.dm[SDRAM + k] = rnd.getrandbits(32) if stale else 0
        if tables:
            for u in range(SYMS['TABLE_SLICES']):
                sim.setR(4, u)
                sim.call(SYMS['FZ_TABLES'])
            sim.wr(SYMS['FZ_G'] + SYMS['G_TAB'], SYMS['TABLE_SLICES'])
        self.knobs(effect_db=effect_db, dry_db=dry_db, mode=mode == 'latch', hold=0, attack=attack, release=release)
        self.instructions = []

    def knobs(self, effect_db=..., dry_db=..., mode=None, hold=None, attack=None, release=None):
        for pid, db in ((SYMS['P_EFFECT'], effect_db), (SYMS['P_DRY'], dry_db)):
            if db is not ...:
                self.sim.wr(I0 + pid, ssim.f2b(-200.0 if db is None else db))
        for pid, v in ((SYMS['P_MODE'], mode), (SYMS['P_HOLD'], hold)):
            if v is not None:
                self.sim.wr(I0 + pid, int(v))
        for pid, v in ((SYMS['P_ATTACK'], attack), (SYMS['P_RELEASE'], release)):
            if v is not None:
                self.sim.wr(I0 + pid, ssim.f2b(v))

    def state(self, name):
        return self.sim.rd(I0 + SYMS[name])

    def call(self, block):
        sim, rnd = self.sim, self.rnd
        for k in range(B):
            sim.wr(BI + k, ssim.f2b(float(block[k])))
        for r in range(16):
            sim.setR(r, rnd.getrandbits(32))
            sim.alt[r] = rnd.getrandbits(32)
            sim.u[0x50 + r] = rnd.getrandbits(32)
        keep = [c for c in range(0x10, 0x50) if c not in (0x10, 0x11, 0x12, 0x13, 0x40, 0x41, 0x42, 0x43)]
        for c in keep:
            sim.set(c, rnd.getrandbits(8) or 1 if 0x30 <= c < 0x40 else rnd.getrandbits(32) & 0xFFFFF)
        for c, v in ((0x10, I0), (0x11, BI), (0x12, self.out), (0x13, ENTRY)):
            sim.set(c, v)
        sim.u[ssim.U_MODE1] |= 0x1000000
        regs = lambda: ([sim.R(r) for r in range(16)], list(sim.alt[:16]), list(sim.u[0x50:0x60]),
                        {c: sim.get(c) for c in keep}, sim.u[ssim.U_MODE1])
        before = regs()
        start = sim.cycles
        sim.call(SYMS['CUSTOM_AMP_ENTRY'], limit=50_000)
        self.instructions.append(sim.cycles - start)
        assert regs() == before, 'registers changed'
        assert not sim.loops and not sim.pcstk
        return np.array([ssim.b2f(sim.rd(self.out + k)) for k in range(B)])

    def run(self, x, holds=None):
        out = []
        for k in range(len(x) // B):
            if holds is not None:
                self.knobs(hold=holds[k])
            out.append(self.call(x[k * B:(k + 1) * B]))
        return np.concatenate(out)

    def ring(self, n):
        return np.array([ssim.b2f(self.sim.rd(SDRAM + k)) for k in range(n)])


def tone(seconds, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(round(seconds * fz.FS)) / fz.FS
    return sum(a * np.cos(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
               for f, a in ((110.0, 0.3), (440.0, 0.1), (1500.0, 0.05), (5000.0, 0.2)))


def decimated(x):
    return np.convolve(x, fz.decimator_taps())[:len(x)][7::8]


@pytest.mark.parametrize('effect_db, dry_db', [(0.0, 0.0), (-6.0, 3.5), (0.0, None), (-60.0, -119.0)])
def test_without_a_press_the_output_is_the_input_times_dry_level(effect_db, dry_db):
    x = tone(0.05)
    k = Kernel(effect_db=effect_db, dry_db=dry_db)
    ref = fz.render(x, np.zeros(len(x) // B, dtype=bool), effect_db=effect_db, dry_db=dry_db)[0]
    assert np.abs(k.run(x) - ref).max() < 1e-6 * np.abs(x).max()


def test_dry_level_moves_over_one_block():
    x = tone(0.01)
    k = Kernel(dry_db=0.0)
    f = fz.Freeze(dry_db=0.0)
    got, want = [], []
    for n in range(len(x) // B):
        if n == 3:
            k.knobs(dry_db=-12.0)
            f.knobs(dry_db=-12.0)
        if n == 7:
            k.knobs(dry_db=None)
            f.knobs(dry_db=None)
        got.append(k.call(x[n * B:(n + 1) * B]))
        want.append(f.process(x[n * B:(n + 1) * B], False))
    assert np.abs(np.concatenate(got) - np.concatenate(want)).max() < 1e-6


def test_the_ring_holds_the_input_decimated_at_samples_7_and_15_of_each_block():
    x = tone(0.1)
    k = Kernel()
    k.run(x)
    want = decimated(x)
    assert np.abs(k.ring(len(want)) - want).max() < 1e-6 * np.abs(want).max()
    assert k.state('S_AT') == len(want) and k.state('S_WRITTEN') == len(want)


def test_the_ring_wraps_and_copies_its_first_samples_after_its_end():
    x = tone(0.2)
    k = Kernel()
    k.call(x[:B])
    k.sim.wr(I0 + SYMS['S_AT'], SYMS['RING'] - 6)
    k.run(x[B:])
    ring = k.ring(SYMS['RING'] + SYMS['MIRROR'])
    want = decimated(x)[2:]
    assert np.abs(ring[SYMS['RING'] - 6:SYMS['RING']] - want[:6]).max() < 1e-6
    assert np.abs(ring[:len(want) - 6] - want[6:]).max() < 1e-6
    assert np.array_equal(ring[SYMS['RING']:], ring[:SYMS['MIRROR']])
    assert k.state('S_AT') == len(want) - 6 and k.state('S_WRITTEN') == min(len(want) + 2, fz.CAPTURE)


def test_the_count_of_samples_written_stops_at_the_capture():
    k = Kernel()
    k.run(np.zeros(800 * B))
    assert k.state('S_WRITTEN') == fz.CAPTURE


def test_stale_words_change_nothing():
    x = tone(0.05)
    a, b = Kernel(stale=True), Kernel(stale=False, seed=2)
    assert np.array_equal(a.run(x), b.run(x))
    n = 2 * len(x) // B
    assert np.array_equal(a.ring(n), b.ring(n))


def test_the_output_may_be_the_inputs_place():
    x = tone(0.02)
    assert np.array_equal(Kernel(out=BI, dry_db=-3.0).run(x), Kernel(dry_db=-3.0).run(x))


def test_the_tables_are_made_over_the_first_calls_before_any_decimation():
    k = Kernel(tables=False)
    made = Kernel()
    for n in range(SYMS['TABLE_SLICES']):
        k.call(np.zeros(B))
        assert k.state('S_WRITTEN') == 0
    for name, size in (('FZ_TAB', 1536), ('FZ_TAPS', fz.TAPS)):
        assert [k.sim.rd(SYMS[name] + i) for i in range(size)] == [made.sim.rd(SYMS[name] + i) for i in range(size)]
    k.call(np.zeros(B))
    assert k.state('S_WRITTEN') == 2


def test_without_its_sdram_block_it_plays_the_input_and_writes_nothing():
    x = tone(0.02)
    k = Kernel(sdram_words=SYMS['SDR_NEED'] - 1, dry_db=-6.0)
    before = k.ring(64)
    assert np.abs(k.run(x) - x * 10 ** (-6 / 20)).max() < 1e-6
    assert np.array_equal(k.ring(64), before, equal_nan=True) and k.state('S_WRITTEN') == 0


def test_instructions_a_call():
    k = Kernel()
    k.run(tone(0.01))
    print(k.instructions[0], max(k.instructions[1:]))
    assert k.instructions[0] < 1500 and max(k.instructions[1:]) < 1000


def harmonics(seconds):
    t = np.arange(round(seconds * fz.FS)) / fz.FS
    return 0.05 * sum(np.cos(2 * np.pi * 110.0 * n * t + 0.3 * n) / n for n in range(1, 25))


def blocks(seconds):
    return round(seconds * fz.FS / B)


def sines(k):
    """The voice's sines in the kernel: frequencies (Hz) and amplitudes."""
    import math
    base = I0 + SYMS['S_SINES'] + SYMS['SINES_N'] * k.state('S_VBUF')
    f, a = [], []
    for i in range(fz.PARTIALS):
        w = base + 10 * (i >> 1) + (i & 1)
        c, s_, inv = (ssim.b2f(k.sim.rd(w + o)) for o in (4, 6, 8))
        f.append(math.atan2(s_, c) * fz.FS / (2 * math.pi))
        a.append(1 / math.sqrt(inv) if inv > 0 else 0.0)
    return np.array(f), np.array(a)


def test_a_grabs_sines_are_the_references_partials():
    """The frequencies within 1e-3 Hz (a sample's turn in float32 is good to about 4e-4 Hz near 2.7 kHz), the
    amplitudes within 2e-4 of theirs, the start phases the golden-ratio pattern's."""
    x = harmonics(0.7)
    holds = np.zeros(len(x) // B, dtype=bool)
    holds[blocks(0.3):] = True
    k = Kernel(attack=0.05)
    f = fz.Freeze(attack=0.05)
    for n in range(blocks(0.3) + fz.LATENCY + 1):
        k.knobs(hold=holds[n])
        k.call(x[n * B:(n + 1) * B])
        f.process(x[n * B:(n + 1) * B], holds[n])
    assert k.state('S_VON') and f.voice
    hz, amp = sines(k)
    assert np.abs(hz - np.angle(f.voice.steps[1]) * fz.FS / (2 * np.pi)).max() < 1e-3
    assert np.abs(amp / f.voice.amp - 1).max() < 2e-4


def test_momentary_grab_plays_the_references_voice():
    """Out to within 1e-3 of the reference over 0.35 s of voice (its frequencies' float32 offsets add up)."""
    x = harmonics(1.0)
    holds = np.zeros(len(x) // B, dtype=bool)
    holds[blocks(0.3):blocks(0.7)] = True
    k = Kernel(attack=0.05, release=0.1)
    got = k.run(x, holds)
    want, f = fz.render(x, holds, attack=0.05, release=0.1)
    assert f.log == [(blocks(0.3), 'grab'), (blocks(0.3) + fz.LATENCY, 'start'), (blocks(0.7), 'release'),
                     (blocks(0.8), 'end')]
    start = (blocks(0.3) + fz.LATENCY) * B
    assert np.abs(got[:start] - want[:start]).max() < 1e-6
    assert np.abs(got - want).max() < 1e-3 * np.abs(want).max()
    assert np.abs(got[blocks(0.8) * B:] - want[blocks(0.8) * B:]).max() < 1e-6
    print(max(k.instructions[1:]))
