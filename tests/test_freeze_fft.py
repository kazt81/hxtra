"""The freeze block's analysis in ssim (src/sharc/freeze.asm): the twiddle table, the windowed capture placed at
bit-reversed points, the complex 1,024-point FFT and the split into the real 2,048-point spectrum's power, against
numpy and tools/sharc/freeze.py."""
import re
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
BINS = range(19, 1006)                       # the powers FZ_SPLIT leaves at FZ_RE + k: k = 19..1005


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
        self.equ = {k: int(v) for k, v in equ.items()}
        self.sim = ssim.Sim()
        self.sim.load(secs)
        self.longest = {}

    def shift(self, name, default):
        return self.equ.get(name, default)

    def run(self, step, slices, capture=None):
        if capture is not None:
            for i, v in enumerate(capture):
                self.sim.wr(IN + i, ssim.f2b(float(v)))
        for u in range(slices):
            self.sim.setR(4, u)
            self.sim.setR(5, IN)
            before = self.sim.cycles
            self.sim.call(self.syms[step], limit=200_000)
            assert not self.sim.loops and not self.sim.pcstk
            self.longest[step] = max(self.longest.get(step, 0), self.sim.cycles - before)

    def floats(self, name, n, at=0):
        return np.array([ssim.b2f(self.sim.rd(self.syms[name] + at + i)) for i in range(n)])

    def spectrum(self, capture):
        self.run('FZ_TABLES', 1)
        self.run('FZ_LOAD', 1024 >> self.shift('LOAD_SHIFT', 6), capture)
        loaded = self.floats('FZ_RE', 2048)
        self.run('FZ_FFT', 5120 >> self.shift('FFT_SHIFT', 7))
        self.run('FZ_SPLIT', -(-494 >> self.shift('SPLIT_SHIFT', 6)))
        return loaded, self.floats('FZ_RE', 2048)[list(BINS)]


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
    loaded, power = a.spectrum(capture)
    return a, capture, loaded, power


def test_the_twiddle_table_is_a_quarter_turn_of_cos_in_2048_steps(harmonics):
    a = harmonics[0]
    assert np.abs(a.floats('FZ_COS', 513) - fz.quarter_wave()).max() < 2e-7


def test_the_load_puts_the_windowed_capture_at_bit_reversed_points(harmonics):
    _, capture, loaded, _ = harmonics
    want = np.zeros(2048)
    want[:fz.CAPTURE] = capture * np.hanning(fz.CAPTURE)
    assert np.abs(unscramble(loaded) - want).max() < 1e-6 * np.abs(capture).max()
    assert not unscramble(loaded)[fz.CAPTURE:].any()


@pytest.mark.parametrize('kind', ['harmonics', 'noise', 'sine', 'silence'])
def test_the_power_is_numpys_for_the_loaded_points(kind):
    a = Analysis()
    loaded, power = a.spectrum(signal(kind))
    want = np.abs(np.fft.rfft(unscramble(loaded)))[list(BINS)] ** 2
    assert np.abs(power - want).max() <= 1e-5 * max(want.max(), 1e-30)


def test_the_power_is_the_references_for_the_capture(harmonics):
    _, capture, _, power = harmonics
    want = np.abs(np.fft.rfft(capture * np.hanning(fz.CAPTURE), fz.NFFT))[list(BINS)] ** 2
    assert np.abs(power - want).max() <= 1e-5 * want.max()
    assert fz.pick(np.concatenate([np.zeros(19), power, np.zeros(19)])) == fz.pick(np.concatenate([np.zeros(19), want,
                                                                                                    np.zeros(19)]))


@pytest.mark.parametrize('equ', [dict(LOAD_SHIFT=3, FFT_SHIFT=5, SPLIT_SHIFT=3), dict(LOAD_SHIFT=10, FFT_SHIFT=9,
                                                                                         SPLIT_SHIFT=9)])
def test_slices_of_any_size_give_the_same_power(harmonics, equ):
    _, capture, _, power = harmonics
    assert np.array_equal(Analysis(**equ).spectrum(capture)[1], power)


def test_instructions_a_slice(harmonics):
    a = harmonics[0]
    print({k: v for k, v in a.longest.items()})
    assert a.longest['FZ_LOAD'] < 1400 and a.longest['FZ_FFT'] < 1700 and a.longest['FZ_SPLIT'] < 1400


def test_no_loop_ends_in_a_branch():
    """The SHARC runs no JUMP, CALL or RTS in a hardware loop's last three instructions (ssim does not model it)."""
    pm = [sec for sec in assemble()[0] if sec.kind == 'pm'][0]
    text = {pm.addr + i: visa_dis.isa_text(w, pm.addr + i) for i, w in enumerate(pm.words)}
    ends = [int(m.group(1), 16) for t in text.values() if (m := re.search(r'DO (0x[0-9a-f]+) UNTIL LCE', t))]
    assert ends
    bad = [(hex(e), text[a]) for e in ends for a in (e - 2, e - 1, e) if re.search(r'\b(JUMP|CALL|RTS)\b', text[a])]
    assert not bad


def test_only_the_tables_are_data_at_boot():
    sections = [sec for sec in assemble()[0] if sec.kind == 'dm']
    assert [len(sec.words) for sec in sections if any(sec.words)] == [34]
    assert sum(len(sec.words) for sec in sections) == 34 + 8 + 750 + 513 + 2048
