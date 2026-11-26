#!/usr/bin/env python3
"""The freeze block's reference: what its kernel does, block by block, in float64.

Every 16-sample block the kernel decimates the input to 6 kHz into a ring (RING samples). A grab analyses the last
CAPTURE ring samples (Hann window, a real NFFT-point FFT), takes the PARTIALS strongest peaks from LO_BIN to HI_BIN, and
plays them as steady sines from `latency` blocks later, so that together they sound CONNECT_DB under the ring's last
LEVEL samples (50 ms). The k-th strongest sine starts at the phase start_phase(k), whatever the input. The sines of a
grab are the voice; there is one. A grab while the voice sounds fades it out over LATENCY blocks, by the time the new
one starts. Out = input x Dry Level + the voice x Effect Level.

decimator_taps() and quarter_wave() are the kernel's tables; pick() and analyse() are the grab;
Freeze is one instance, with a log of what each press did. oscillate_f32() runs the kernel's sine recurrence in
float32, for its long-term drift.
"""
import math

import numpy as np

FS = 48000
BLOCK = 16
DEC = 8                            # 48 kHz to 6 kHz
FS_DEC = FS // DEC
TAPS = 127
CUT = 2750.0                       # the decimator's cutoff, and the top of the analysis
RING = 2048                        # 6 kHz samples kept
CAPTURE = 1500                     # samples a grab analyses: 0.25 s
NFFT = 2048
HZ = FS_DEC / NFFT                 # 2.93 Hz a bin
LO_BIN = int(60.0 / HZ)            # 20: 58.6 Hz
HI_BIN = int(CUT / HZ)             # 938 (not taken): peaks up to 2,745 Hz
GAP = 3                            # bins: a peak is taken only if more than this from every one taken
PARTIALS = 32
CONNECT_DB = -4.0                  # the voice's level against the input's just before the grab
LEVEL = 300                        # ring samples the input's level is measured on: the last 50 ms
DOUBLE = 0.3                       # seconds: a Latch press this soon after a grabbing press stops everything
TWIDDLES = 2048                    # the quarter-wave table's steps (the FFT's twiddles)
LATENCY = 150                      # blocks from a grab to its sound (50 ms), and the fade of a voice a grab cuts
GOLDEN = (math.sqrt(5.0) - 1.0) / 2.0


def decimator_taps():
    """The 127-tap lowpass before the decimation: a Hamming-windowed sinc at CUT, its taps summing to 1."""
    n = np.arange(TAPS) - TAPS // 2
    h = np.sinc(2.0 * CUT / FS * n) * np.hamming(TAPS)
    return h / h.sum()


def quarter_wave():
    """cos(2 pi k / TWIDDLES) for k = 0..TWIDDLES/4: the kernel's table (FZ_COS) for its FFT."""
    return np.cos(2.0 * np.pi * np.arange(TWIDDLES // 4 + 1) / TWIDDLES)


def bit_reverse(n, bits=10):
    """n with its low `bits` bits in reverse order: where the FFT's input point n goes."""
    return int(format(n, f'0{bits}b')[::-1], 2)


def start_phase(k):
    """The phase (radians, of a cosine) the k-th strongest sine of a grab starts at: the fractional part of k times the
    golden ratio, of a turn. The 32 are spread over the turn, no two closer than 1/47 of it."""
    return 2.0 * math.pi * (k * GOLDEN % 1.0)


def pick(p):
    """The bins a grab takes from the power spectrum p: the peaks from LO_BIN to HI_BIN (above the bin below, not below
    the bin above), strongest first (the lower bin on a tie), each more than GAP bins from every one taken, PARTIALS at
    most."""
    k = np.arange(LO_BIN, HI_BIN)
    cand = k[(p[k] > p[k - 1]) & (p[k] >= p[k + 1])]
    taken = []
    for b in sorted(cand.tolist(), key=lambda b: (-p[b], b)):
        if all(abs(b - t) > GAP for t in taken):
            taken.append(b)
            if len(taken) == PARTIALS:
                break
    return taken


def analyse(capture, power):
    """The partials of a grab: [(frequency in Hz, amplitude)], strongest first, scaled so that their RMS is the input's
    (power: its mean square) CONNECT_DB down. capture: the last CAPTURE 6 kHz samples, oldest first. Empty when there is
    nothing to play (no peak, or no input)."""
    v = np.asarray(capture, dtype=float)
    assert len(v) == CAPTURE
    w = np.hanning(CAPTURE)
    p = np.abs(np.fft.rfft(v * w, NFFT)) ** 2
    taken = pick(p)
    if not taken or power <= 0.0:
        return []
    db = 10.0 * np.log10(np.maximum(p, 1e-300))
    found = []
    for b in taken:
        a, m, z = db[b - 1], db[b], db[b + 1]
        den = a - 2.0 * m + z
        d = 0.5 * (a - z) / den if den != 0.0 else 0.0
        found.append(((b + d) * HZ, 2.0 * 10.0 ** ((m - 0.25 * (a - z) * d) / 20.0) / w.sum()))
    gain = math.sqrt(power) * 10.0 ** (CONNECT_DB / 20.0) / math.sqrt(sum(g[1] ** 2 for g in found) / 2.0)
    return [(f, amp * gain) for f, amp in found]


def ramp(k, n):
    """0 at k = 0 up to 1 at k >= n, in a straight line."""
    return min(k, n) / n


class Voice:
    """One grab: its sines and its envelope, attack x release x steal, each a ramp counted in blocks."""

    def __init__(self, partials, attack_blocks, start):
        f = np.array([g[0] for g in partials])
        self.amp = np.array([g[1] for g in partials])
        w = np.exp(2j * np.pi * f / FS)
        self.steps = w[None, :] ** np.arange(BLOCK)[:, None]        # w^j for the block's 16 samples
        self.w16 = w ** BLOCK
        self.z = np.exp(1j * np.array([start_phase(k) for k in range(len(f))]))      # c + i s
        self.start, self.attack = start, attack_blocks
        self.rel = self.steal = None                               # (start block, length in blocks)

    def env(self, n):
        """The envelope at the start of block n."""
        e = ramp(n - self.start, self.attack)
        for cut in (self.rel, self.steal):
            if cut:
                e *= 1.0 - ramp(n - cut[0], cut[1])
        return e

    def ended(self, n):
        return any(cut and n - cut[0] >= cut[1] for cut in (self.rel, self.steal))

    def block(self, n):
        """The block's 16 samples, envelope included; the sines then move on a block, their size set back to 1."""
        e0, e1 = self.env(n), self.env(n + 1)
        env = e0 + (e1 - e0) * np.arange(BLOCK) / BLOCK
        out = (self.steps * self.z[None, :]).real @ self.amp * env
        self.z = self.z * self.w16
        self.z /= np.abs(self.z)
        return out


class Freeze:
    """One instance. process(block, hold) takes 16 input samples and the Hold state and returns 16 output samples.
    log: (block, what) for each grab, start, empty (a grab with nothing to play), release, steal, cancel and end.
    latency: blocks from a grab to its voice, LATENCY or more (more when the kernel's analysis had to wait)."""

    def __init__(self, mode='momentary', attack=0.3, release=1.0, effect_db=0.0, dry_db=0.0, latency=LATENCY):
        assert latency >= LATENCY                          # (a voice a grab cuts is gone when the new one starts)
        self.mode, self.attack, self.release, self.latency = mode, attack, release, latency
        self.effect, self.dry = self._gain(effect_db), self._gain(dry_db)
        self.taps = decimator_taps()
        self.hist = np.zeros(TAPS - 1)
        self.ring, self.at = np.zeros(RING), 0
        self.voice = None
        self.pending = None                                # (start block, partials) of a grab in analysis
        self.hold, self.n = False, 0
        self.last_press, self.last_grabbed = None, False
        self.log = []

    @staticmethod
    def _gain(db):
        return 0.0 if db is None else 10.0 ** (db / 20.0)

    def knobs(self, effect_db=..., dry_db=...):
        """Effect Level and Dry Level; the new gain is reached over the next block."""
        self._next = (self.effect if effect_db is ... else self._gain(effect_db),
                      self.dry if dry_db is ... else self._gain(dry_db))

    def blocks(self, seconds):
        return max(1, round(seconds * FS / BLOCK))

    def _capture(self):
        idx = (self.at - CAPTURE + np.arange(CAPTURE)) % RING
        return self.ring[idx]

    def _release(self):
        if self.pending:
            self.pending = None
            self.log.append((self.n, 'cancel'))
        elif self.voice and not self.voice.rel and not self.voice.steal:
            self.voice.rel = (self.n, self.blocks(self.release))
            self.log.append((self.n, 'release'))

    def _grab(self):
        capture = self._capture()
        partials = analyse(capture, float(np.mean(capture[-LEVEL:] ** 2)))
        if self.voice and not self.voice.steal:           # (one already fading out keeps its fade)
            self.voice.steal = (self.n, LATENCY)
            self.log.append((self.n, 'steal'))
        self.pending = (self.n + self.latency, partials)
        self.log.append((self.n, 'grab'))

    def _press(self):
        if self.mode == 'latch':
            stop = self.last_grabbed and (self.n - self.last_press) * BLOCK <= DOUBLE * FS
            self._release()
            if not stop:
                self._grab()
            self.last_grabbed = not stop
            self.last_press = self.n
        else:
            self._grab()

    def process(self, block, hold):
        x = np.asarray(block, dtype=float)
        assert len(x) == BLOCK
        if hold and not self.hold:
            self._press()
        if self.mode == 'momentary' and not hold:
            self._release()
        self.hold = hold
        if self.voice and self.voice.ended(self.n):
            self.voice = None
            self.log.append((self.n, 'end'))
        if self.pending and self.pending[0] == self.n:
            _, partials = self.pending
            self.pending = None
            if partials:
                self.voice = Voice(partials, self.blocks(self.attack), self.n)
                self.log.append((self.n, 'start'))
            else:
                self.log.append((self.n, 'empty'))
        wet = self.voice.block(self.n) if self.voice else np.zeros(BLOCK)
        g = np.arange(BLOCK) / BLOCK
        effect0, dry0 = self.effect, self.dry
        if hasattr(self, '_next'):
            self.effect, self.dry = self._next
            del self._next
        out = x * (dry0 + (self.dry - dry0) * g) + wet * (effect0 + (self.effect - effect0) * g)
        buf = np.concatenate([self.hist, x])
        for j in (7, 15):
            self.ring[self.at] = buf[j:j + TAPS] @ self.taps
            self.at = (self.at + 1) % RING
        self.hist = buf[BLOCK:]
        self.n += 1
        return out


def render(x, holds, **knobs):
    """The output for input x (a multiple of 16 samples) with holds: a Hold state per block. Returns (out, Freeze)."""
    fz = Freeze(**knobs)
    x = np.asarray(x, dtype=float)
    out = np.concatenate([fz.process(x[k * BLOCK:(k + 1) * BLOCK], bool(h)) for k, h in enumerate(holds)])
    return out, fz


def oscillate_f32(freqs, blocks, phase=0.0):
    """The kernel's sines in float32: each (c, s) turned by (cos w, sin w) every sample, its size set back to 1 at the
    end of every block by x (1.5 - 0.5 (c^2 + s^2)). Returns c + i s at the end of each block, (blocks, len(freqs))."""
    f32 = np.float32
    w = 2.0 * np.pi * np.asarray(freqs, dtype=float) / FS
    C, S = np.cos(w).astype(f32), np.sin(w).astype(f32)
    c, s = np.full(len(w), math.cos(phase), dtype=f32), np.full(len(w), math.sin(phase), dtype=f32)
    half, three_halves = f32(0.5), f32(1.5)
    out = np.empty((blocks, len(w)), dtype=complex)
    for n in range(blocks):
        for _ in range(BLOCK):
            c, s = c * C - s * S, s * C + c * S
        k = three_halves - half * (c * c + s * s)
        c, s = c * k, s * k
        out[n] = c + 1j * s.astype(float)
    return out
