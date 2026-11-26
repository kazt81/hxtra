"""The freeze block's reference (tools/sharc/freeze.py): its decimator, the grab's analysis, the voice's level, start
phases and envelope, what each press does in Momentary and Latch, and the kernel's sines in float32."""
import math

import numpy as np
import pytest

import freeze as fz

FS = fz.FS
B = fz.BLOCK
L = fz.LATENCY


def tone(freqs, amps, seconds, fs=FS, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(round(seconds * fs)) / fs
    return sum(a * np.cos(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) for f, a in zip(freqs, amps))


def blocks(seconds):
    return round(seconds * FS / B)


def holds(total, *spans):
    """A Hold state per block over `total` seconds: held from a to b for each (a, b) in seconds."""
    h = np.zeros(blocks(total), dtype=bool)
    for a, b in spans:
        h[blocks(a):blocks(b)] = True
    return h


def presses(total, *at):
    """Latch presses: a block-long press at each time in seconds."""
    return holds(total, *((a, a + B / FS) for a in at))


HARMONICS = 110.0 * np.arange(1, 25), 1.0 / np.arange(1, 25)      # 110 Hz to 2,640 Hz
STEADY = tone(*HARMONICS, 4.0) * 0.05


# ---- the decimator and its tables

def test_the_decimator_is_127_symmetric_taps_summing_to_1():
    h = fz.decimator_taps()
    assert len(h) == 127 and np.allclose(h, h[::-1]) and h.sum() == pytest.approx(1.0)


def response_db(f):
    h = fz.decimator_taps()
    return 20 * np.log10(np.abs(np.exp(-2j * np.pi * np.outer(f, np.arange(fz.TAPS)) / FS) @ h))


def test_the_decimator_is_flat_to_2_khz_half_down_at_2_75_khz_and_stops_from_3_4_khz():
    assert np.abs(response_db(np.linspace(0, 2000, 401))).max() < 0.05
    assert response_db([fz.CUT])[0] == pytest.approx(-6.0, abs=0.1)
    assert response_db(np.linspace(3400, FS / 2, 4001)).max() < -50


def test_the_ring_holds_the_input_filtered_and_kept_at_samples_7_and_15_of_each_block():
    x = tone([440.0, 1500.0, 5000.0], [0.3, 0.2, 0.4], 0.1)
    f = fz.Freeze()
    for k in range(len(x) // B):
        f.process(x[k * B:(k + 1) * B], False)
    full = np.convolve(x, fz.decimator_taps())[:len(x)]
    kept = full[7::8]
    assert np.allclose(f.ring[:len(kept)], kept)


def test_a_grab_analyses_the_1500_ring_samples_before_the_press_block_and_levels_on_their_last_50_ms(monkeypatch):
    seen = []
    monkeypatch.setattr(fz, 'analyse', lambda cap, power: seen.append((cap.copy(), power)) or [])
    press = blocks(0.5)
    fz.render(STEADY[:blocks(0.6) * B], holds(0.6, (0.5, 0.6)))
    kept = np.convolve(STEADY, fz.decimator_taps())[:len(STEADY)][7::8]
    (cap, power), = seen
    assert np.allclose(cap, kept[2 * press - fz.CAPTURE:2 * press])
    assert power == pytest.approx(np.mean(kept[2 * press - 300:2 * press] ** 2))


# ---- the grab

def capture(freqs, amps, seed=0):
    return tone(freqs, amps, fz.CAPTURE / fz.FS_DEC, fs=fz.FS_DEC, seed=seed)[:fz.CAPTURE]


def test_a_grab_takes_the_strongest_partials_first_within_0_05_hz_and_0_1_db():
    f, a = HARMONICS
    got = sorted(fz.analyse(capture(f, a), float(np.sum(a * a) / 2))[:24])      # (the order goes by the peak's bin)
    hz = np.array([g[0] for g in got])
    amp = np.array([g[1] for g in got])
    assert np.abs(hz - f).max() < 0.05
    assert np.abs(20 * np.log10(amp / amp[0]) - 20 * np.log10(a / a[0])).max() < 0.1


def test_a_grab_fills_the_32_with_weaker_peaks_after_the_partials():
    f, a = HARMONICS
    got = fz.analyse(capture(f, a), float(np.sum(a * a) / 2))
    assert len(got) == 32
    assert max(g[1] for g in got[24:]) < min(g[1] for g in got[:24])           # the window's sidelobes


def test_a_grab_comes_in_4_db_under_the_input():
    f, a = HARMONICS
    power = float(np.sum(a * a) / 2)
    got = fz.analyse(capture(f, a), power)
    assert 20 * math.log10(math.sqrt(sum(g[1] ** 2 for g in got) / 2) / math.sqrt(power)) == pytest.approx(-4.0)


def test_a_grab_keeps_more_than_3_bins_between_partials():
    near = fz.analyse(capture([500.0, 500.0 + 2.5 * fz.HZ], [1.0, 0.5]), 1.0)
    apart = fz.analyse(capture([500.0, 500.0 + 4.5 * fz.HZ], [1.0, 0.5]), 1.0)
    assert near[0][0] == pytest.approx(500.0, abs=1.0) and all(abs(g[0] - 500 - 2.5 * fz.HZ) > 3 for g in near[1:])
    assert [round(g[0]) for g in apart[:2]] == [500, round(500 + 4.5 * fz.HZ)]


def peaks(*bins_powers):
    p = np.full(fz.NFFT // 2 + 1, 1e-6)
    for b, v in bins_powers:
        p[b] = v
    return p


def test_pick_takes_a_peak_only_more_than_3_bins_from_a_stronger_one():
    assert fz.pick(peaks((300, 1.0), (303, 0.5))) == [300]
    assert fz.pick(peaks((300, 1.0), (304, 0.5))) == [300, 304]
    assert fz.pick(peaks((300, 1.0), (297, 0.5), (295, 0.25))) == [300, 295]      # (one left out blocks nothing)


def test_pick_goes_strongest_first_and_takes_the_lower_bin_on_a_tie():
    assert fz.pick(peaks((500, 0.5), (400, 1.0), (600, 0.5))) == [400, 500, 600]


def test_pick_keeps_to_bins_20_to_937():
    assert fz.pick(peaks((20, 1.0), (937, 1.0))) == [20, 937]
    assert fz.pick(peaks((19, 9.0), (100, 1.0), (938, 9.0))) == [100]


def test_a_grab_takes_32_at_most():
    f = 60.0 * np.arange(1, 46)
    got = fz.analyse(capture(f, np.ones(45)), 1.0)
    assert len(got) == 32
    assert sorted(round(g[0] / 60) for g in got) == sorted(set(round(g[0] / 60) for g in got))


def test_a_grab_leaves_out_what_is_below_58_6_hz_or_above_2745_hz():
    got = fz.analyse(capture([50.0, 440.0, 2760.0], [1.0, 0.1, 1.0]), 1.0)
    assert got[0][0] == pytest.approx(440.0, abs=0.05)
    assert all(abs(g[0] - 50) > 3 and abs(g[0] - 2760) > 3 for g in got)
    assert fz.LO_BIN * fz.HZ == pytest.approx(58.6, abs=0.05) and (fz.HI_BIN - 1) * fz.HZ < 2745.5


def test_a_grab_of_silence_plays_nothing():
    assert fz.analyse(np.zeros(fz.CAPTURE), 0.0) == []
    x = tone([440.0], [0.1], 0.5)
    out, f = fz.render(np.concatenate([np.zeros(blocks(0.5) * B), x]), holds(1.0, (0.1, 0.4)))
    a = blocks(0.1)
    assert f.log == [(a, 'grab'), (a + L, 'empty')]
    assert np.array_equal(out[blocks(0.5) * B:], x)


# ---- the voices

def test_the_voice_sounds_4_db_under_the_input_after_the_attack():
    out, f = fz.render(STEADY, holds(4.0, (1.0, 4.0)), dry_db=None)
    start = blocks(1.0) + L
    wet = out[(start + f.blocks(0.3)) * B:(start + f.blocks(0.3)) * B + FS]
    dry = STEADY[blocks(0.75) * B:blocks(1.0) * B]
    assert 20 * math.log10(np.sqrt(np.mean(wet ** 2)) / np.sqrt(np.mean(dry ** 2))) == pytest.approx(-4.0, abs=0.2)


def test_the_start_phases_are_the_golden_ratio_pattern():
    assert [fz.start_phase(k) for k in range(4)] == pytest.approx(
        [0.0, 2 * math.pi * 0.6180339887, 2 * math.pi * 0.2360679775, 2 * math.pi * 0.8541019662])
    turn = sorted(fz.start_phase(k) / (2 * math.pi) for k in range(fz.PARTIALS))
    assert np.diff(turn + [turn[0] + 1]).min() > 1 / 47
    f = fz.Freeze()
    for k in range(blocks(1.0) + L + 1):
        f.process(STEADY[k * B:(k + 1) * B], k >= blocks(1.0))
    assert f.log[-1] == (blocks(1.0) + L, 'start')
    start = f.voice.z * f.voice.w16.conj()                            # (its first block has turned it on a block)
    assert start == pytest.approx(np.exp(1j * np.array([fz.start_phase(k) for k in range(fz.PARTIALS)])))


@pytest.mark.parametrize('freq', [220.0, 440.0, 1240.0])       # (whole periods in the level's 50 ms)
def test_each_sine_starts_at_its_phase_whatever_the_inputs(freq):
    t = np.arange(blocks(2.0) * B) / FS
    start = blocks(1.0) + L
    got = []
    for phase in (0.0, 1.0, 2.5):
        out, _ = fz.render(0.3 * np.cos(2 * np.pi * freq * t + phase), holds(2.0, (1.0, 2.0)), dry_db=None)
        got.append(out[start * B:])
    assert np.abs(got[1] - got[0]).max() < 1e-3 * np.abs(got[0]).max()
    assert np.abs(got[2] - got[0]).max() < 1e-3 * np.abs(got[0]).max()


def test_attack_and_release_are_straight_lines_in_blocks():
    _, f = fz.render(STEADY[:blocks(0.6) * B], holds(0.6, (0.1, 0.6)), attack=0.1, release=0.2)
    v = f.voice
    n_a = f.blocks(0.1)
    assert [v.env(v.start + k) for k in range(n_a + 2)] == pytest.approx([min(k, n_a) / n_a for k in range(n_a + 2)])
    v.rel = (v.start + n_a + 10, f.blocks(0.2))
    n_r = f.blocks(0.2)
    assert [v.env(v.start + n_a + 10 + k) for k in range(n_r + 2)] == pytest.approx(
        [1 - min(k, n_r) / n_r for k in range(n_r + 2)])


def test_the_envelope_is_a_straight_line_within_a_block():
    _, f = fz.render(STEADY[:blocks(0.3) * B], holds(0.3, (0.1, 0.3)), attack=0.05, dry_db=None)
    v = f.voice
    v.amp[:] = 0.0
    v.amp[0] = 1.0
    v.z[:] = 1.0
    v.steps[:] = 1.0                                   # a sine frozen at 1: the output is the envelope
    n = v.start + 3
    assert v.block(n) == pytest.approx(v.env(n) + (v.env(n + 1) - v.env(n)) * np.arange(B) / B)


def test_each_block_sets_the_sines_back_to_size_1():
    _, f = fz.render(STEADY[:blocks(1.3) * B], holds(1.3, (1.0, 1.3)))
    v = f.voice
    v.z = v.z * np.linspace(0.9, 1.1, len(v.z))
    v.block(f.n)
    assert np.abs(v.z) == pytest.approx(np.ones(len(v.z)), abs=1e-15)


def test_dry_level_and_effect_level_move_over_one_block():
    f = fz.Freeze(dry_db=0.0)
    f.knobs(dry_db=-6.0)
    out = f.process(np.ones(B), False)
    g = 10 ** (-6 / 20)
    assert out == pytest.approx(1 + (g - 1) * np.arange(B) / B)
    assert f.process(np.ones(B), False) == pytest.approx(np.full(B, g))
    _, f = fz.render(STEADY[:blocks(1.0) * B], holds(1.0, (0.1, 1.0)), dry_db=None)
    wet = f.voice.block(f.n)
    f.voice.z = f.voice.z * f.voice.w16.conj()      # (the same block again)
    f.knobs(effect_db=-12.0)
    out = f.process(np.zeros(B), True)
    assert out == pytest.approx(wet * (1 + (10 ** (-12 / 20) - 1) * np.arange(B) / B))


# ---- Momentary

def test_momentary_plays_while_held_and_releases_when_let_go():
    _, f = fz.render(STEADY, holds(4.0, (1.0, 2.0)), release=0.5)
    on, off = blocks(1.0), blocks(2.0)
    assert f.log == [(on, 'grab'), (on + L, 'start'), (off, 'release'), (off + f.blocks(0.5), 'end')]


def test_momentary_let_go_during_the_analysis_cancels_the_grab():
    _, f = fz.render(STEADY[:blocks(2.0) * B], holds(2.0, (1.0, 1.0 + 10 * B / FS)))
    on = blocks(1.0)
    assert f.log == [(on, 'grab'), (on + 10, 'cancel')]


def test_a_press_while_the_voice_releases_fades_it_out_over_the_latency():
    _, f = fz.render(STEADY, holds(4.0, (1.0, 1.5), (1.7, 2.5)), release=0.5)
    b = blocks(1.7)
    assert f.log[:7] == [(blocks(1.0), 'grab'), (blocks(1.0) + L, 'start'), (blocks(1.5), 'release'), (b, 'steal'),
                         (b, 'grab'), (b + L, 'end'), (b + L, 'start')]


# ---- Latch

def test_latch_holds_after_the_press_and_a_press_grabs_again():
    _, f = fz.render(STEADY, presses(4.0, 1.0, 2.0), mode='latch', release=0.5)
    a, b = blocks(1.0), blocks(2.0)
    assert f.log == [(a, 'grab'), (a + L, 'start'), (b, 'release'), (b, 'steal'), (b, 'grab'), (b + L, 'end'),
                     (b + L, 'start')]


def test_latch_double_press_stops_everything_the_first_press_grabbed_too():
    _, f = fz.render(STEADY, presses(4.0, 1.0, 2.0, 2.2), mode='latch', release=0.5)
    b, c = blocks(2.0), blocks(2.2)
    assert [e for e in f.log if e[0] >= b] == [(b, 'release'), (b, 'steal'), (b, 'grab'), (b + L, 'end'),
                                               (b + L, 'start'), (c, 'release'), (c + f.blocks(0.5), 'end')]


@pytest.mark.parametrize('gap, stops', [(900, True), (901, False)])
def test_latch_double_press_counts_up_to_0_3_s_inclusive(gap, stops):
    h = np.zeros(blocks(4.0), dtype=bool)
    h[[blocks(1.0), blocks(1.0) + gap]] = True
    _, f = fz.render(STEADY, h, mode='latch')
    assert ((blocks(1.0) + gap, 'grab') in f.log) is not stops


def test_latch_double_press_within_the_analysis_cancels_the_grab():
    _, f = fz.render(STEADY, presses(4.0, 1.0, 1.0 + 20 * B / FS), mode='latch')
    a = blocks(1.0)
    assert f.log == [(a, 'grab'), (a + 20, 'cancel')]


def test_latch_press_after_a_stop_grabs_however_soon():
    _, f = fz.render(STEADY, presses(4.0, 1.0, 1.2, 1.3), mode='latch', release=0.5)
    c = blocks(1.3)
    assert (c, 'grab') in f.log


def test_a_grab_fades_the_voice_out_in_a_straight_line_by_the_time_the_new_one_starts():
    out, f = fz.render(STEADY, presses(4.0, 1.0, 2.0), mode='latch', release=3.0)
    b = blocks(2.0)
    old = f.log.index((b, 'steal'))
    assert f.log[old:] == [(b, 'steal'), (b, 'grab'), (b + L, 'end'), (b + L, 'start')]
    f2 = fz.Freeze(mode='latch', release=3.0)
    for k in range(b + 1):
        f2.process(STEADY[k * B:(k + 1) * B], k in (blocks(1.0), b))
    v, n_r = f2.voice, f2.blocks(3.0)
    assert [v.env(b + k) for k in range(L + 1)] == pytest.approx(
        [(1 - k / n_r) * (1 - k / L) for k in range(L + 1)])


def test_a_grab_of_nothing_still_fades_the_voice_out():
    x = STEADY.copy()
    x[blocks(1.5) * B:] = 0.0
    _, f = fz.render(x, presses(4.0, 1.0, 2.0), mode='latch', release=3.0)
    b = blocks(2.0)
    assert [e for e in f.log if e[0] >= b] == [(b, 'release'), (b, 'steal'), (b, 'grab'), (b + L, 'end'),
                                               (b + L, 'empty')]


def test_a_voice_already_fading_out_is_not_cut_again():
    h = np.zeros(blocks(4.0), dtype=bool)
    a, b = blocks(1.0), blocks(2.0)
    h[[a, b, b + 10, b + 20]] = True                     # a grab steals; a stop cancels it; a grab follows
    _, f = fz.render(STEADY, h, mode='latch', release=3.0)
    assert [e for e in f.log if e[1] == 'steal'] == [(b, 'steal')]
    assert [e for e in f.log if e[0] > b] == [(b + 10, 'cancel'), (b + 20, 'grab'), (b + L, 'end'),
                                              (b + 20 + L, 'start')]


def test_a_later_start_keeps_the_fade_at_the_latency():
    _, f = fz.render(STEADY, presses(4.0, 1.0, 2.0), mode='latch', release=3.0, latency=L + 30)
    b = blocks(2.0)
    assert [e for e in f.log if e[0] >= b] == [(b, 'release'), (b, 'steal'), (b, 'grab'), (b + L, 'end'),
                                               (b + L + 30, 'start')]


def test_a_latency_under_the_fade_is_refused():
    with pytest.raises(AssertionError):
        fz.Freeze(latency=L - 1)


def test_switching_to_latch_keeps_the_held_voice():
    f = fz.Freeze()
    for k in range(blocks(2.0)):
        f.process(STEADY[k * B:(k + 1) * B], k >= blocks(1.0))
    f.mode = 'latch'
    for k in range(blocks(2.0), blocks(3.0)):
        f.process(STEADY[k * B:(k + 1) * B], False)
    assert [what for _, what in f.log] == ['grab', 'start']


def test_switching_to_momentary_without_hold_releases_a_latched_voice():
    f = fz.Freeze(mode='latch')
    x = STEADY
    for k in range(blocks(2.0)):
        f.process(x[k * B:(k + 1) * B], k == blocks(1.0))
    f.mode = 'momentary'
    f.process(x[:B], False)
    assert f.log[-1] == (blocks(2.0), 'release')


# ---- the kernel's sines in float32

def test_the_sines_keep_their_size_and_pitch_in_float32():
    freqs = [58.6, 220.0, 440.0, 1234.5, 2745.0]
    n = blocks(10.0)
    z = fz.oscillate_f32(freqs, n)
    assert np.abs(np.abs(z) - 1).max() < 1e-5
    exact = np.exp(2j * np.pi * np.outer(np.arange(1, n + 1), freqs) * B / FS)
    drift = np.unwrap(np.angle(z * exact.conj()), axis=0)           # radians behind (or ahead of) the exact sine
    cents = 1200 * np.log2(1 + (drift[-1] - drift[0]) / (n - 1) / (2 * np.pi * np.array(freqs) * B / FS))
    assert np.abs(cents).max() < 0.01
