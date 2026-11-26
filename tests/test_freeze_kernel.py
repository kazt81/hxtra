"""The freeze block's kernel (src/sharc/freeze.asm) in ssim, call by call, against tools/sharc/freeze.py: the registers,
the levels, the decimator and its ring in SDRAM, the first call and the tables made over the first calls; a grab's
sines, the two voices in Momentary and Latch, the turn between instances, FZ_TAB made again after a grab, and the
load's EP DMA (nam_multi.ChainDma, which models a standard DMA too)."""
import random
import re
from pathlib import Path

import numpy as np
import pytest

import freeze as fz
import nam_multi
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
    SDRAM block stale (random). call() runs one block and checks that no register changed. With `share`, a second
    instance in the same simulator (at other addresses), its turn and tables shared."""

    def __init__(self, effect_db=0.0, dry_db=0.0, tables=True, sdram_words=SDR_WORDS, stale=True, out=None, seed=1,
                 mode='momentary', attack=0.3, release=1.0, share=None, odd=False):
        k = 0 if share is None else 1
        self.i0, self.bi, self.entry, self.sdram = I0 + 0x400 * k, BI + 0x200 * k, ENTRY + 0x100 * k, SDRAM + 0x2000 * k
        self.i0 += odd
        self.out = (BO + 0x200 * k) if out is None else out
        if share is None:
            self.sim = sim = ssim.Sim()
            sim.strict_cbufen = True
            sim.load(SECS)
            self.dma = nam_multi.ChainDma(sim)
            self.rnd = rnd = random.Random(seed)
        else:
            sim, rnd = share.sim, share.rnd
            self.sim, self.dma, self.rnd = sim, share.dma, rnd
            tables = False
        self.make(stale, sdram_words)
        if tables:
            for u in range(SYMS['TABLE_SLICES']):
                sim.setR(4, u)
                sim.call(SYMS['FZ_TABLES'])
            sim.wr(SYMS['FZ_G'] + SYMS['G_TAB'], SYMS['TABLE_SLICES'])
        self.knobs(effect_db=effect_db, dry_db=dry_db, mode=mode == 'latch', hold=0, attack=attack, release=release)
        self.instructions = []
        self.dmac0 = 0                          # DMAC0 after each call: the kernel leaves the channel off

    def make(self, stale=True, sdram_words=SDR_WORDS):
        """The instance as the stock makes it (again)."""
        sim, rnd = self.sim, self.rnd
        for k in range(145):
            sim.wr(self.i0 + k, 0)
        sim.wr(self.i0 + 3, 1)
        for k in range(145, SYMS['DM_WORDS']):
            sim.dm[self.i0 + k] = rnd.getrandbits(32) if stale else 0
        sim.wr(self.entry + 2, self.entry + 0x10)
        sim.wr(self.entry + 0x10 + 6, self.sdram)
        sim.wr(self.entry + 0x10 + 7, self.sdram + sdram_words)
        for k in range(SDR_WORDS):
            sim.dm[self.sdram + k] = rnd.getrandbits(32) if stale else 0

    def knobs(self, effect_db=..., dry_db=..., mode=None, hold=None, attack=None, release=None):
        for pid, db in ((SYMS['P_EFFECT'], effect_db), (SYMS['P_DRY'], dry_db)):
            if db is not ...:
                self.sim.wr(self.i0 + pid, ssim.f2b(-200.0 if db is None else db))
        for pid, v in ((SYMS['P_MODE'], mode), (SYMS['P_HOLD'], hold)):
            if v is not None:
                self.sim.wr(self.i0 + pid, int(v))
        for pid, v in ((SYMS['P_ATTACK'], attack), (SYMS['P_RELEASE'], release)):
            if v is not None:
                self.sim.wr(self.i0 + pid, ssim.f2b(v))

    def state(self, name, voice=0):
        return self.sim.rd(self.i0 + SYMS[name] + SYMS['VOICE'] * voice)

    def g(self, name):
        return self.sim.rd(SYMS['FZ_G'] + SYMS[name])

    def call(self, block):
        sim, rnd = self.sim, self.rnd
        for k in range(B):
            sim.wr(self.bi + k, ssim.f2b(float(block[k])))
        for r in range(16):
            sim.setR(r, rnd.getrandbits(32))
            sim.alt[r] = rnd.getrandbits(32)
            sim.u[0x50 + r] = rnd.getrandbits(32)
        keep = [c for c in range(0x10, 0x50) if c not in (0x10, 0x11, 0x12, 0x13, 0x40, 0x41, 0x42, 0x43)]
        for c in keep:
            sim.set(c, rnd.getrandbits(8) or 1 if 0x30 <= c < 0x40 else rnd.getrandbits(32) & 0xFFFFF)
        for c, v in ((0x10, self.i0), (0x11, self.bi), (0x12, self.out), (0x13, self.entry)):
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
        assert sim.rd(nam_multi.DMAC0) == self.dmac0, 'the DMA channel left on'
        return np.array([ssim.b2f(sim.rd(self.out + k)) for k in range(B)])

    def run(self, x, holds=None):
        out = []
        for k in range(len(x) // B):
            if holds is not None:
                self.knobs(hold=holds[k])
            out.append(self.call(x[k * B:(k + 1) * B]))
        return np.concatenate(out)

    def ring(self, n):
        return np.array([ssim.b2f(self.sim.rd(self.sdram + k)) for k in range(n)])


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
    assert k.instructions[0] < 1700 and max(k.instructions[1:]) < 1000


def harmonics(seconds):
    t = np.arange(round(seconds * fz.FS)) / fz.FS
    return 0.05 * sum(np.cos(2 * np.pi * 110.0 * n * t + 0.3 * n) / n for n in range(1, 25))


def blocks(seconds):
    return round(seconds * fz.FS / B)


def sines(k, v):
    """The sines of voice v in the kernel: c + i s (amplitude and phase), frequencies (Hz) and amplitudes."""
    return set_sines(k, sines_base(k, k.state('V_BUF', v)))


def sines_base(k, n):
    """Where set n of the sines starts: I0 + S_SINES rounded up to even, then 160 n on."""
    return ((k.i0 + SYMS['S_SINES'] + 1) & ~1) + SYMS['SINES_N'] * n


def set_sines(k, base):
    z, f, a = [], [], []
    for i in range(fz.PARTIALS):
        w = base + 10 * (i >> 1) + (i & 1)
        c, s_, cw, sw, h = (ssim.b2f(k.sim.rd(w + o)) for o in (0, 2, 4, 6, 8))
        z.append(complex(c, s_))
        f.append(np.angle(complex(cw, sw)) * fz.FS / (2 * np.pi))
        a.append(np.sqrt(0.5 / h) if h > 0 else 0.0)
    return np.array(z), np.array(f), np.array(a)


def test_a_grabs_sines_are_the_references_partials():
    """Before the voice starts: the frequencies within 1e-3 Hz (a sample's turn in float32 is good to about 4e-4 Hz
    near 2.7 kHz), the amplitudes within 2e-4 of theirs, c + i s (a sample before the voice's first) within 1e-3 of
    a e^(i (phase - w))."""
    x = harmonics(0.7)
    holds = np.zeros(len(x) // B, dtype=bool)
    holds[blocks(0.3):] = True
    k = Kernel(attack=0.05)
    f = fz.Freeze(attack=0.05)
    for n in range(blocks(0.3) + fz.LATENCY):
        k.knobs(hold=holds[n])
        k.call(x[n * B:(n + 1) * B])
        f.process(x[n * B:(n + 1) * B], holds[n])
    assert k.state('S_PEND') and k.state('S_DONE') == 1 and k.state('S_PV') == 0
    _, partials, phases = f.pending[0]
    z, hz, amp = set_sines(k, sines_base(k, k.state('S_PBUF')))
    ref_f, ref_a = np.array([g[0] for g in partials]), np.array([g[1] for g in partials])
    assert np.abs(hz - ref_f).max() < 1e-3
    assert np.abs(amp / ref_a - 1).max() < 2e-4
    w = 2 * np.pi * ref_f / fz.FS
    assert np.abs(z - ref_a * np.exp(1j * (np.array(phases) - w))).max() < 1e-3 * ref_a.max()


@pytest.mark.slow
def test_momentary_grab_plays_the_references_voice():
    """Out to within 1e-3 of the reference over 0.35 s of voice (its frequencies' float32 offsets add up)."""
    x = harmonics(1.0)
    holds = np.zeros(len(x) // B, dtype=bool)
    holds[blocks(0.3):blocks(0.7)] = True
    k = Kernel(attack=0.05, release=0.1)
    got = k.run(x, holds)
    want, f = fz.render(x, holds, attack=0.05, release=0.1)
    assert f.log == [(blocks(0.3), 'grab', 0), (blocks(0.3) + fz.LATENCY, 'start', 0), (blocks(0.7), 'release', 0),
                     (blocks(0.8), 'end', 0)]
    start = (blocks(0.3) + fz.LATENCY) * B
    assert np.abs(got[:start] - want[:start]).max() < 1e-6
    assert np.abs(got - want).max() < 1e-3 * np.abs(want).max()
    assert np.abs(got[blocks(0.8) * B:] - want[blocks(0.8) * B:]).max() < 1e-6
    print(max(k.instructions[1:]))


# ---- two voices, the turn, the table made again, EP DMA: the kernel against the reference, block by block

L = fz.LATENCY


def holding(seconds, *spans):
    """A Hold state per block over `seconds`: held from a to b (seconds) for each (a, b); b None: to the end."""
    h = np.zeros(blocks(seconds), dtype=bool)
    for a, b in spans:
        h[blocks(a):None if b is None else blocks(b)] = True
    return h


def pressing(seconds, *at):
    """Latch presses: a block-long press at each time (seconds)."""
    h = np.zeros(blocks(seconds), dtype=bool)
    h[[blocks(a) for a in at]] = True
    return h


def both(x, holds, mode='momentary', attack=0.05, release=0.1, **levels):
    """The kernel and the reference on the same input and Hold states: (kernel's out, reference's out, Kernel,
    Freeze)."""
    k = Kernel(mode=mode, attack=attack, release=release, **levels)
    got = k.run(x[:len(holds) * B], holds)
    want, f = fz.render(x[:len(holds) * B], holds, mode=mode, attack=attack, release=release, **levels)
    return got, want, k, f


def assert_close(got, want, tol=1e-3):
    assert np.abs(got - want).max() <= tol * np.abs(want).max()


@pytest.mark.parametrize('second_db, stolen', [(0.0, 0), (-20.0, 1)])
@pytest.mark.slow
def test_momentary_takes_the_other_voice_then_steals_the_quieter(second_db, stolen):
    """Three holds, each let go: the second grab takes voice 1 while voice 0 releases; the third, both releasing, takes
    the quieter by envelope x level (the older one at the same level, the second when its input was 20 dB down) and
    fades it out over LATENCY blocks. Also the most instructions a call takes, two voices sounding and a grab's
    analysis running."""
    x = harmonics(0.8)
    x[blocks(0.36) * B:blocks(0.5) * B] *= 10 ** (second_db / 20)
    h = holding(0.8, (0.3, 0.38), (0.42, 0.5), (0.55, 0.62))
    got, want, k, f = both(x, h, release=1.0)
    c = blocks(0.55)
    assert [e for e in f.log if e[0] == c] == [(c, 'steal', stolen), (c, 'grab', stolen)]
    assert (c + L, 'start', stolen) in f.log
    assert_close(got, want)
    print(max(k.instructions[1:]))
    assert max(k.instructions[1:]) < 6000


@pytest.mark.slow
def test_latch_grabs_again_a_double_press_stops_everything_and_the_next_press_grabs():
    """Latch: a press grabs (voice 0); one 0.32 s on grabs again (voice 1, voice 0 releases); one 0.15 s after that
    stops everything; one 0.08 s after the stop grabs. Effect Level and Dry Level move on the way."""
    x = harmonics(1.1)
    h = pressing(1.1, 0.3, 0.62, 0.77, 0.85)
    k = Kernel(mode='latch', attack=0.05, release=0.1)
    f = fz.Freeze(mode='latch', attack=0.05, release=0.1)
    got, want = [], []
    for n in range(len(h)):
        if n == blocks(0.5):
            k.knobs(effect_db=-6.0, dry_db=-3.0)
            f.knobs(effect_db=-6.0, dry_db=-3.0)
        k.knobs(hold=h[n])
        got.append(k.call(x[n * B:(n + 1) * B]))
        want.append(f.process(x[n * B:(n + 1) * B], h[n]))
    c, d = blocks(0.77), blocks(0.85)
    assert [(what, v) for _, what, v in f.log] == [('grab', 0), ('start', 0), ('release', 0), ('grab', 1),
                                                   ('start', 1), ('end', 0), ('release', 1), ('grab', 0),
                                                   ('end', 1), ('start', 0)]
    assert (c, 'release', 1) in f.log and (d, 'grab', 0) in f.log
    assert_close(np.concatenate(got), np.concatenate(want))


@pytest.mark.parametrize('gap, stops', [(900, True), (901, False)])
def test_latch_double_press_counts_up_to_0_3_s_inclusive(gap, stops):
    """(The last press's block set back, so that the second press comes `gap` blocks after the first.)"""
    x = harmonics(0.4)
    k = Kernel(mode='latch')
    a = blocks(0.3)
    k.run(x[:a * B], pressing(0.3 + B / fz.FS, 0.3)[:a])
    k.knobs(hold=1)
    k.call(x[a * B:(a + 1) * B])
    assert k.state('S_PEND') and k.state('S_GRABBED')
    k.knobs(hold=0)
    k.run(x[(a + 1) * B:(a + 20) * B])
    k.sim.wr(k.i0 + SYMS['S_LASTP'], a + 20 - gap)
    k.knobs(hold=1)
    k.call(x[(a + 20) * B:(a + 21) * B])
    assert bool(k.state('S_PEND')) is not stops and bool(k.state('S_GRABBED')) is not stops


@pytest.mark.slow
def test_switching_modes_keeps_a_held_voice_and_releases_a_latched_one_without_hold():
    """Momentary held, then Latch while held: the voice stays after Hold goes up. Momentary again without Hold:
    it releases."""
    x = harmonics(0.75)
    k = Kernel(attack=0.05, release=0.1)
    f = fz.Freeze(attack=0.05, release=0.1)
    h = holding(0.75, (0.3, 0.5))
    got, want = [], []
    for n in range(len(h)):
        if n == blocks(0.45):
            k.knobs(mode=1)
            f.mode = 'latch'
        if n == blocks(0.6):
            k.knobs(mode=0)
            f.mode = 'momentary'
        k.knobs(hold=h[n])
        got.append(k.call(x[n * B:(n + 1) * B]))
        want.append(f.process(x[n * B:(n + 1) * B], h[n]))
    assert f.log == [(blocks(0.3), 'grab', 0), (blocks(0.3) + L, 'start', 0), (blocks(0.6), 'release', 0),
                     (blocks(0.6) + f.blocks(0.1), 'end', 0)]
    assert_close(np.concatenate(got), np.concatenate(want))


@pytest.mark.slow
def test_a_grab_of_silence_fades_the_quieter_voice_out_and_plays_nothing():
    x = harmonics(0.85)
    x[blocks(0.51) * B:] = 0.0
    h = holding(0.85, (0.3, 0.38), (0.42, 0.5), (0.6, None))
    got, want, k, f = both(x, h, release=1.0)
    c = blocks(0.6)
    assert [e for e in f.log if e[0] >= c] == [(c, 'steal', 0), (c, 'grab', 0), (c + L, 'end', 0),
                                               (c + L, 'empty', 0)]
    assert_close(got, want)
    assert k.state('S_DONE') == 2 and not k.state('S_PEND') and not k.state('V_ON', 0)


def tab(k):
    return [k.sim.rd(SYMS['FZ_TAB'] + i) for i in range(1536)]


def test_a_grab_let_go_during_its_candidates_makes_the_table_again():
    """FZ_TAB holds the candidates from the candidates' step on; a grab cancelled then has the table made again, a
    slice a call, before any grab takes the turn."""
    x = harmonics(0.6)
    k = Kernel(release=0.1)
    made = tab(k)
    n = blocks(0.3)
    k.run(x[:n * B])
    k.knobs(hold=1)
    while not (k.g('G_STEP') == 5 and k.g('G_OWNER')):
        k.call(x[n * B:(n + 1) * B])
        n += 1
    assert k.g('G_REB') == SYMS['TAB_SLICES'] and k.g('G_OWNER') == k.i0
    k.knobs(hold=0)
    k.call(x[n * B:(n + 1) * B])
    assert not k.state('S_PEND') and k.g('G_OWNER') == 0 and k.g('G_REB') == SYMS['TAB_SLICES'] - 1
    k.knobs(hold=1)                                  # a grab now waits for the table
    for m in range(n + 1, n + SYMS['TAB_SLICES']):
        k.call(x[m * B:(m + 1) * B])
        assert k.g('G_OWNER') == 0 and k.state('S_PEND')
    assert k.g('G_REB') == 0 and tab(k) == made
    k.call(x[(m + 1) * B:(m + 2) * B])
    assert k.g('G_OWNER') == k.i0


def latency_of_the_grab_at(k, x, h, press):
    """Runs the kernel over Hold states h; returns its output and the latency of the grab pressed at block `press`
    (from its start, known once its analysis is done)."""
    got, latency = [], None
    for n in range(len(h)):
        k.knobs(hold=h[n])
        got.append(k.call(x[n * B:(n + 1) * B]))
        if n >= press and latency is None and k.state('S_PEND') and k.state('S_DONE'):
            latency = k.state('S_PSTART') - press
    return np.concatenate(got), latency


@pytest.mark.slow
def test_a_grab_while_the_table_is_made_again_starts_late_as_the_reference_with_that_latency():
    """A Momentary grab held just past its start, then another: the second waits for FZ_TAB, made again after the
    first, and starts later than LATENCY, as the reference with that latency."""
    x = harmonics(0.9)
    a = blocks(0.3)
    b = a + L + 8
    h = np.zeros(blocks(0.9), dtype=bool)
    h[a:a + L + 4] = True
    h[b:] = True
    k = Kernel(attack=0.05, release=0.1)
    got, latency = latency_of_the_grab_at(k, x, h, b)
    assert latency > L
    f = fz.Freeze(attack=0.05, release=0.1)
    want = []
    for n in range(len(h)):
        if n == b:
            f.latency = latency
        want.append(f.process(x[n * B:(n + 1) * B], h[n]))
    assert (b + latency, 'start', 1) in f.log
    assert_close(got, np.concatenate(want))


@pytest.mark.slow
def test_two_instances_pressed_together_take_turns():
    """Two instances pressed at the same block: the second waits for the first's analysis and the table made again,
    then plays as the reference with that latency."""
    x = harmonics(1.0)
    y = 0.7 * harmonics(1.0)[::-1].copy()
    a = blocks(0.3)
    h = holding(1.0, (0.3, None))
    k1 = Kernel(attack=0.05, release=0.1)
    k2 = Kernel(attack=0.05, release=0.1, share=k1)
    got1, got2, latency = [], [], None
    for n in range(len(h)):
        k1.knobs(hold=h[n])
        k2.knobs(hold=h[n])
        got1.append(k1.call(x[n * B:(n + 1) * B]))
        got2.append(k2.call(y[n * B:(n + 1) * B]))
        if latency is None and k2.state('S_PEND') and k2.state('S_DONE'):
            latency = k2.state('S_PSTART') - a
    assert latency > L + SYMS['TAB_SLICES']
    want1 = fz.render(x[:len(h) * B], h, attack=0.05, release=0.1)[0]
    want2 = fz.render(y[:len(h) * B], h, attack=0.05, release=0.1, latency=latency)[0]
    assert_close(np.concatenate(got1), want1)
    assert_close(np.concatenate(got2), want2)
    print(max(k1.instructions[1:] + k2.instructions[1:]))


@pytest.mark.parametrize('made_again', [False, True])
def test_an_owner_deleted_or_made_again_gives_up_its_turn(made_again):
    """The owner's block deleted (no call since the other's last call): the other takes the turn at its next call. Made
    again at the same place: its first call frees the turn, which the other takes."""
    x = harmonics(0.4)
    k1 = Kernel()
    k2 = Kernel(share=k1)
    n = blocks(0.3)
    for m in range(n):
        k1.call(x[m * B:(m + 1) * B])
        k2.call(x[m * B:(m + 1) * B])
    k1.knobs(hold=1)
    k2.knobs(hold=1)
    for m in range(n, n + 5):
        k1.call(x[m * B:(m + 1) * B])
        k2.call(x[m * B:(m + 1) * B])
    assert k1.g('G_OWNER') == k1.i0 and k2.state('S_PEND') and k2.g('G_STEP') == 1
    k1.make()
    if made_again:
        k1.call(x[:B])
        assert k1.g('G_OWNER') == 0 and not k1.state('S_PEND')
    k2.call(x[:B])
    assert k2.g('G_OWNER') == k2.i0 and k2.g('G_STEP') == 1 and k2.g('G_SLICE') == 0


def test_a_busy_dma_channel_puts_the_load_slice_off_a_call():
    """The channel busy (DEN set by another kernel) or its interrupt open: the load slice waits a call, nothing moved,
    DMAC0 left as it was."""
    x = harmonics(0.4)
    k = Kernel()
    n = blocks(0.3)
    k.run(x[:n * B])
    k.knobs(hold=1)
    k.call(x[n * B:(n + 1) * B])                    # the zeroing
    assert k.g('G_STEP') == 1 and k.g('G_SLICE') == 0
    k.dma.wr0(nam_multi.DMAC0, nam_multi.DEN)        # (as left by another kernel: the model starts nothing)
    k.dmac0 = nam_multi.DEN
    chains = len(k.dma.chains)
    k.call(x[(n + 1) * B:(n + 2) * B])
    assert k.g('G_STEP') == 1 and k.g('G_SLICE') == 0 and len(k.dma.chains) == chains
    k.dma.wr0(nam_multi.DMAC0, 0)
    k.dmac0 = 0
    writes = len(k.dma.writes)
    k.call(x[(n + 2) * B:(n + 3) * B])
    assert k.g('G_SLICE') == 1 and len(k.dma.chains) == chains + 1
    first = (k.state('S_PAT') - fz.CAPTURE) % SYMS['RING']
    m = nam_multi
    assert k.dma.writes[writes:] == [(m.DMAC0, m.DFLSH), (m.CPEP0, 0), (m.IIEP0, SYMS['FZ_STAGE']), (m.IMEP0, 1),
                                     (m.EMEP0, 1), (m.ICEP0, 2 << SYMS['LOAD_SHIFT']), (m.EIEP0, k.sdram + first),
                                     (m.DMAC0, m.DEN), (m.DMAC0, 0)]
    assert [k.sim.rd(SYMS['FZ_STAGE'] + i) for i in range(2 << SYMS['LOAD_SHIFT'])] == \
        [k.sim.rd(k.sdram + first + i) for i in range(2 << SYMS['LOAD_SHIFT'])]


def test_a_dma_that_never_ends_cancels_the_grab():
    x = harmonics(0.4)
    k = Kernel()
    n = blocks(0.3)
    k.run(x[:n * B])
    k.dma.mode = 'stall'
    k.knobs(hold=1)
    got = k.run(x[n * B:(n + 3) * B], [1, 1, 1])
    assert k.g('G_FAIL') == 1 and k.g('G_OWNER') == 0 and not k.state('S_PEND')
    assert np.abs(got - x[n * B:(n + 3) * B]).max() < 1e-6


def test_an_odd_i0_plays_as_an_even_one_with_the_sines_at_even_addresses():
    """The stock may give an odd I0; the sines, read and written two words at a time (SIMD), start at an even address
    all the same, and the output is the even I0's to the bit."""
    x = harmonics(0.45)
    holds = holding(0.45, (0.3, None))
    k, j = Kernel(attack=0.05), Kernel(attack=0.05, odd=True)
    assert k.i0 % 2 == 0 and j.i0 % 2 == 1
    assert np.array_equal(k.run(x, holds), j.run(x, holds))
    assert j.state('V_ON', 0) and sines_base(j, j.state('V_BUF', 0)) % 2 == 0
    assert np.array_equal(sines(j, 0)[0], sines(k, 0)[0])


def test_a_moved_sdram_block_starts_the_ring_again_and_cancels_a_grab():
    """The SDRAM block's start not the last call's: the ring starts again in the new block (nothing old is grabbed)
    and a grab in analysis is cancelled, its turn freed."""
    x = harmonics(0.4)
    k = Kernel()
    n = blocks(0.3)
    k.run(x[:n * B])
    k.knobs(hold=1)
    k.run(x[n * B:(n + 3) * B], [1, 1, 1])
    assert k.state('S_PEND') and k.g('G_OWNER') == k.i0 and k.state('S_WRITTEN') == fz.CAPTURE
    moved = SDRAM + 0x4000
    k.sim.wr(k.entry + 0x10 + 6, moved)
    k.sim.wr(k.entry + 0x10 + 7, moved + SDR_WORDS)
    k.call(x[(n + 3) * B:(n + 4) * B])
    assert not k.state('S_PEND') and k.g('G_OWNER') == 0
    assert k.state('S_SDR') == moved and k.state('S_AT') == 2 and k.state('S_WRITTEN') == 2
    want = decimated(x[:(n + 4) * B])[-2:]
    got = [ssim.b2f(k.sim.rd(moved + i)) for i in range(2)]
    assert np.abs(np.array(got) - want).max() < 1e-6
