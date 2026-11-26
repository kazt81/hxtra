"""The freeze block's analysis in ssim (src/sharc/freeze.asm): the tables (the cos table and the decimator's taps), the
windowed capture placed at bit-reversed points, the complex 1,024-point FFT and the split into the real 2,048-point
spectrum, against numpy and tools/sharc/freeze.py."""
import math
import re
import struct
from pathlib import Path

import numpy as np
import pytest

import freeze as fz
import sasm
import ssim
import visa_dis

ROOT = Path(__file__).resolve().parent.parent
ASM = ROOT / 'src' / 'sharc' / 'freeze.asm'
DM, PM, IN = 0xC0000, 0x8C200, 0xB8000
BINS = range(19, 1006)                       # the spectrum FZ_SPLIT leaves at FZ_RE + k and FZ_IM + k: k = 19..1005
NAN = 0x7FC00001


def assemble(**equ):
    src = ASM.read_text().replace('FZ_DM_BASE', f'{DM:#x}').replace('FZ_PM_BASE', f'{PM:#x}')
    for k, v in equ.items():
        src, n = re.subn(rf'^\.equ {k},\s*\S+', f'.equ {k}, {v}', src, flags=re.M)
        assert n == 1, k
    return sasm.assemble(src, 'freeze.asm')


class Analysis:
    """The analysis's steps in one simulator; each run() calls a step once a slice and keeps the longest slice's count
    of instructions."""

    def __init__(self, **equ):
        secs, self.syms = assemble(**equ)
        self.sim = ssim.Sim()
        self.sim.load(secs)
        self.longest = {}

    def run(self, step, slices, regs=lambda u: {}):
        for u in range(slices):
            self.sim.setR(4, u)
            for r, v in regs(u).items():
                self.sim.setR(r, v)
            before = self.sim.cycles
            self.sim.call(self.syms[step], limit=200_000)
            assert not self.sim.loops and not self.sim.pcstk
            self.longest[step] = max(self.longest.get(step, 0), self.sim.cycles - before)

    def floats(self, name, n, at=0):
        return np.array([ssim.b2f(self.sim.rd(self.syms[name] + at + i)) for i in range(n)])

    def tables(self):
        self.run('FZ_TABLES', self.syms['TABLE_SLICES'])

    def load(self, capture, written=0):
        """The capture at IN, then FZ_ZERO and FZ_LOAD; samples before `written` hold NaNs."""
        for i, v in enumerate(capture):
            self.sim.wr(IN + i, NAN if i < written else ssim.f2b(float(v)))
        self.run('FZ_ZERO', 1)
        n = 2 << self.syms['LOAD_SHIFT']
        self.run('FZ_LOAD', self.syms['LOAD_SLICES'], lambda u: {5: IN + n * u, 7: written})
        return self.floats('FZ_RE', 2048)

    def spectrum(self, capture):
        self.tables()
        loaded = self.load(capture)
        self.run('FZ_FFT', self.syms['FFT_SLICES'])
        self.run('FZ_SPLIT', self.syms['SPLIT_SLICES'])
        x = self.floats('FZ_RE', 1024) + 1j * self.floats('FZ_IM', 1024)
        return loaded, x[list(BINS)]


def unscramble(loaded):
    """The windowed capture back from FZ_RE and FZ_IM (loaded): point n is at rev10(n), x[2n] its real part, x[2n + 1]
    its imaginary part."""
    x = np.empty(2048)
    for n in range(1024):
        x[2 * n], x[2 * n + 1] = loaded[fz.bit_reverse(n)], loaded[1024 + fz.bit_reverse(n)]
    return x


def signal(kind, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(fz.CAPTURE) / fz.FS_DEC
    if kind == 'noise':
        return rng.normal(0, 0.1, fz.CAPTURE)
    if kind == 'silence':
        return np.zeros(fz.CAPTURE)
    if kind == 'sine':
        return 0.3 * np.cos(2 * np.pi * 441.3 * t + 0.7)
    f = 110.0 * np.arange(1, 25)
    return sum(0.05 / n * np.cos(2 * np.pi * fn * t + rng.uniform(0, 2 * np.pi)) for n, fn in enumerate(f, 1))


@pytest.fixture(scope='module')
def harmonics():
    a = Analysis()
    capture = signal('harmonics')
    loaded, x = a.spectrum(capture)
    return a, capture, loaded, x


def test_the_table_is_cos_from_a_quarter_turn_back_in_2048_steps(harmonics):
    a = harmonics[0]
    assert np.abs(a.floats('FZ_TAB', 1536) - np.cos(2 * np.pi * (np.arange(1536) - 512) / 2048)).max() < 2e-7


def test_the_taps_are_the_references(harmonics):
    a = harmonics[0]
    h = fz.decimator_taps()
    assert np.abs(a.floats('FZ_TAPS', fz.TAPS) - h).max() < 1e-6 * h.max()


def test_fz_cos_is_cos_of_turns_of_any_size():
    a = Analysis()
    t = np.concatenate([np.linspace(-3.0, 3.0, 241), [0.0, 0.25, 0.5, 1e-7, 1234.5678, -0.12345]])
    got = []
    for v in t:
        a.sim.setR(0, ssim.f2b(float(np.float32(v))))
        a.sim.call(a.syms['FZ_COS'])
        got.append(ssim.b2f(a.sim.R(0)))
    want = np.cos(2 * np.pi * t.astype(np.float32).astype(float))
    assert np.abs(np.array(got) - want).max() < 3e-7 * max(1.0, np.abs(t).max() / 4)


def test_the_load_puts_the_windowed_capture_at_bit_reversed_points(harmonics):
    """(The window turns from each slice's cos and sin without its size set back: within 1.5e-6 over 128 samples.)"""
    _, capture, loaded, _ = harmonics
    want = np.zeros(2048)
    want[:fz.CAPTURE] = capture * np.hanning(fz.CAPTURE)
    assert np.abs(unscramble(loaded) - want).max() < 2e-6 * np.abs(capture).max()
    assert not unscramble(loaded)[fz.CAPTURE:].any()


@pytest.mark.parametrize('written', [1, 37, 64, 999])
def test_samples_not_written_yet_load_as_zeros(harmonics, written):
    a, capture, _, _ = harmonics
    got = unscramble(a.load(capture, written))
    want = np.zeros(2048)
    want[written:fz.CAPTURE] = (capture * np.hanning(fz.CAPTURE))[written:]
    assert np.abs(got - want).max() < 2e-6 * np.abs(capture).max()


@pytest.mark.parametrize('kind', ['harmonics', 'noise', 'sine', 'silence'])
def test_the_spectrum_is_numpys_for_the_loaded_points(kind):
    a = Analysis()
    loaded, x = a.spectrum(signal(kind))
    want = np.fft.rfft(unscramble(loaded))[list(BINS)]
    assert np.abs(x - want).max() <= 1e-5 * max(np.abs(want).max(), 1e-30)


def test_the_spectrum_is_the_references_for_the_capture(harmonics):
    _, capture, _, x = harmonics
    want = np.fft.rfft(capture * np.hanning(fz.CAPTURE), fz.NFFT)[list(BINS)]
    assert np.abs(x - want).max() <= 1e-5 * np.abs(want).max()
    pad = np.zeros(19)
    assert fz.pick(np.concatenate([pad, np.abs(x) ** 2, pad])) == fz.pick(np.concatenate([pad, np.abs(want) ** 2, pad]))


@pytest.mark.parametrize('equ', [dict(FFT_N=32, SPLIT_SHIFT=3, TAB_SHIFT=3, TAP_SHIFT=2),
                                 dict(FFT_N=1024, SPLIT_SHIFT=9, TAB_SHIFT=9, TAP_SHIFT=6)])
def test_slices_of_any_size_give_the_same_tables_and_spectrum(harmonics, equ):
    a, capture, _, x = harmonics
    b = Analysis(**equ)
    assert np.array_equal(b.spectrum(capture)[1], x)
    for name, n in (('FZ_TAB', 1536), ('FZ_TAPS', fz.TAPS)):
        assert np.array_equal(b.floats(name, n), a.floats(name, n))


@pytest.mark.parametrize('shift', [5, 10])
def test_load_slices_of_any_size_give_the_same_points_but_for_rounding(harmonics, shift):
    """(Each load slice starts its window from cos and sin of its first sample, so the rounding moves with the slices,
    and the window's size drifts with the slice's length. A slice holds 32 points or more: it starts each a = n >> 5 at
    j = 0.)"""
    a, capture, loaded, _ = harmonics
    b = Analysis(LOAD_SHIFT=shift)
    b.tables()
    assert np.abs(b.load(capture) - loaded).max() < 3e-6 * 2 ** max(0, shift - 6) * np.abs(capture).max()


def test_instructions_a_slice(harmonics):
    a = harmonics[0]
    print(a.longest)
    assert max(a.longest.values()) < 1700


def test_no_loop_ends_in_a_branch():
    """The SHARC runs no JUMP, CALL or RTS in a hardware loop's last three instructions (ssim does not model it)."""
    pm = [sec for sec in assemble()[0] if sec.kind == 'pm'][0]
    text = {pm.addr + i: visa_dis.isa_text(w, pm.addr + i) for i, w in enumerate(pm.words)}
    ends = [int(m.group(1), 16) for t in text.values() if (m := re.search(r'DO (0x[0-9a-f]+) UNTIL LCE', t))]
    assert ends
    bad = [(hex(e), text[a]) for e in ends for a in (e - 2, e - 1, e) if re.search(r'\b(JUMP|CALL|RTS)\b', text[a])]
    assert not bad


def test_only_the_bit_reversal_the_rotation_and_the_steps_are_data_at_boot():
    sections = [sec for sec in assemble()[0] if sec.kind == 'dm']
    assert [len(sec.words) for sec in sections if any(sec.words)] == [32 + 2 + 16]
    assert sum(len(sec.words) for sec in sections) == 50 + 64 + 24 + 1 + 32 + 17 + 32 + 128 + 8 + 1536 + fz.TAPS + 2048
    rot = [struct.unpack('<f', struct.pack('<I', w))[0] for w in sections[0].words[32:34]]
    assert rot == pytest.approx([math.cos(2 * math.pi / 1499), math.sin(2 * math.pi / 1499)])
