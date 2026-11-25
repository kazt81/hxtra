#!/usr/bin/env python3
"""The freeze block's reference: what its kernel does, block by block, in float64.

Every 16-sample block the kernel decimates the input to 6 kHz into a ring (RING samples). A grab analyses the last
CAPTURE ring samples (Hann window, a real NFFT-point FFT), takes the PARTIALS strongest peaks from LO_BIN to HI_BIN, and
plays them as steady sines from `latency` blocks later, so that together they sound CONNECT_DB under the ring's last
LEVEL samples (50 ms). Each sine starts 90 degrees on from the input's own partial (in quadrature), so that it neither
cancels nor reinforces the input still sounding. Each grab is a voice; there are VOICES of them, so that a Latch
re-grab can fade one sound out while the next fades in. Out = input x Dry Level + the voices x Effect Level.

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
RING = 2048                        # 6 kHz samples kept (the kernel's SDRAM ring)
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
VOICES = 2
PHASES = 1024                      # start phases
TWIDDLES = 2048                    # the quarter-wave table's steps (the FFT's twiddles; the start phases every other)
LATENCY = 48                       # blocks from a grab to its sound: the analysis (a guess until the kernel is written)
DELAY = TAPS // 2                  # the decimator's delay, in 48 kHz samples


def decimator_taps():
    """The 127-tap lowpass before the decimation: a Hamming-windowed sinc at CUT, its taps summing to 1."""
    n = np.arange(TAPS) - TAPS // 2
    h = np.sinc(2.0 * CUT / FS * n) * np.hamming(TAPS)
    return h / h.sum()


def quarter_wave():
    """cos(2 pi k / TWIDDLES) for k = 0..TWIDDLES/4: the kernel's table (FZ_COS) for its FFT and the sines' start
    phases."""
    return np.cos(2.0 * np.pi * np.arange(TWIDDLES // 4 + 1) / TWIDDLES)


def cos_sin(k, n=PHASES):
    """cos and sin of 2 pi k / n read from quarter_wave(), as the kernel reads them."""
    q, k, step = quarter_wave(), k % n, TWIDDLES // n
    quad, r = divmod(k, n // 4)
    c, s = q[r * step], q[(n // 4 - r) * step]
    return ((c, s), (-s, c), (-c, -s), (s, -c))[quad]


def bit_reverse(n, bits=10):
    """n with its low `bits` bits in reverse order: where the FFT's input point n goes."""
    return int(format(n, f'0{bits}b')[::-1], 2)


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
    """The partials of a grab: [(frequency in Hz, amplitude, phase)], strongest first, scaled so that their RMS is the
    input's (power: its mean square) CONNECT_DB down; phase: the partial's at the capture's first sample (radians, of a
    cosine). capture: the last CAPTURE 6 kHz samples, oldest first. Empty when there is nothing to play (no peak, or no
    input)."""
    v = np.asarray(capture, dtype=float)
    assert len(v) == CAPTURE
    w = np.hanning(CAPTURE)
    x = np.fft.rfft(v * w, NFFT)
    p = np.abs(x) ** 2
    taken = pick(p)
    if not taken or power <= 0.0:
        return []
    db = 10.0 * np.log10(np.maximum(p, 1e-300))
    found = []
    for b in taken:
        a, m, z = db[b - 1], db[b], db[b + 1]
        den = a - 2.0 * m + z
        d = 0.5 * (a - z) / den if den != 0.0 else 0.0
        phase = float(np.angle(x[b])) - 2.0 * math.pi * d * (CAPTURE - 1) / 2.0 / NFFT   # (the window's centre)
        found.append(((b + d) * HZ, 2.0 * 10.0 ** ((m - 0.25 * (a - z) * d) / 20.0) / w.sum(), phase))
    gain = math.sqrt(power) * 10.0 ** (CONNECT_DB / 20.0) / math.sqrt(sum(g[1] ** 2 for g in found) / 2.0)
    return [(f, amp * gain, phase) for f, amp, phase in found]


def raised_cosine(k, n):
    """0 at k = 0 up to 1 at k >= n."""
    return 0.5 - 0.5 * math.cos(math.pi * min(k, n) / n)


class Voice:
    """One grab: its sines and its envelope, attack x release x steal, each a raised cosine counted in blocks."""

    def __init__(self, partials, phases, attack_blocks, start):
        f = np.array([g[0] for g in partials])
        self.amp = np.array([g[1] for g in partials])
        self.level = math.sqrt(float(np.sum(self.amp ** 2)) / 2.0)   # its RMS, envelope at 1
        w = np.exp(2j * np.pi * f / FS)
        self.steps = w[None, :] ** np.arange(BLOCK)[:, None]        # w^j for the block's 16 samples
        self.w16 = w ** BLOCK
        self.z = np.array([complex(*cos_sin(k)) for k in phases])  # c + i s
        self.start, self.attack = start, attack_blocks
        self.rel = self.steal = None                               # (start block, length in blocks)

    def env(self, n):
        """The envelope at the start of block n."""
        e = raised_cosine(n - self.start, self.attack)
        for cut in (self.rel, self.steal):
            if cut:
                e *= 1.0 - raised_cosine(n - cut[0], cut[1])
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
    log: (block, what, voice) for each grab, start, release, steal, cancel and end."""

    def __init__(self, mode='momentary', attack=0.3, release=1.0, effect_db=0.0, dry_db=0.0, latency=LATENCY):
        self.mode, self.attack, self.release, self.latency = mode, attack, release, latency
        self.effect, self.dry = self._gain(effect_db), self._gain(dry_db)
        self.taps = decimator_taps()
        self.hist = np.zeros(TAPS - 1)
        self.ring, self.at = np.zeros(RING), 0
        self.voices = [None] * VOICES
        self.pending = [None] * VOICES                     # (start block, partials, phases) of a grab in analysis
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

    def _release(self, v):
        voice = self.voices[v]
        if self.pending[v]:
            self.pending[v] = None
            self.log.append((self.n, 'cancel', v))
        elif voice and not voice.rel and not voice.steal:
            voice.rel = (self.n, self.blocks(self.release))
            self.log.append((self.n, 'release', v))

    def _grab(self):
        capture = self._capture()
        partials = analyse(capture, float(np.mean(capture[-LEVEL:] ** 2)))
        if not partials:
            return None
        # from the capture's first sample (ring sample 2n - CAPTURE: output 8m + 7, input DELAY earlier) to the voice's
        # first, in 48 kHz samples; then 90 degrees on
        ahead = BLOCK * (self.n + self.latency) - (DEC * (2 * self.n - CAPTURE) + 7 - DELAY)
        phases = [round((phase + 2.0 * math.pi * f / FS * ahead + math.pi / 2) / (2.0 * math.pi) * PHASES) % PHASES
                  for f, _, phase in partials]
        free = [v for v in range(VOICES) if self.voices[v] is None and self.pending[v] is None]
        if free:
            v = free[0]
        else:
            v = min((v for v in range(VOICES) if self.pending[v] is None),
                    key=lambda v: (self.voices[v].env(self.n) * self.voices[v].level, v))
            if not self.voices[v].steal:              # (one already fading out keeps its fade)
                self.voices[v].steal = (self.n, self.latency)
                self.log.append((self.n, 'steal', v))
        self.pending[v] = (self.n + self.latency, partials, phases)
        self.log.append((self.n, 'grab', v))
        return v

    def _press(self):
        if self.mode == 'latch':
            if self.last_grabbed and (self.n - self.last_press) * BLOCK <= DOUBLE * FS:
                for v in range(VOICES):
                    self._release(v)
                self.last_grabbed = False
            else:
                for v in range(VOICES):
                    self._release(v)
                self._grab()
                self.last_grabbed = True
            self.last_press = self.n
        else:
            self._grab()

    def process(self, block, hold):
        x = np.asarray(block, dtype=float)
        assert len(x) == BLOCK
        if hold and not self.hold:
            self._press()
        if self.mode == 'momentary' and not hold:
            for v in range(VOICES):
                self._release(v)
        self.hold = hold
        for v in range(VOICES):
            if self.voices[v] and self.voices[v].ended(self.n):
                self.voices[v] = None
                self.log.append((self.n, 'end', v))
            if self.pending[v] and self.pending[v][0] == self.n:
                _, partials, phases = self.pending[v]
                self.pending[v] = None
                self.voices[v] = Voice(partials, phases, self.blocks(self.attack), self.n)
                self.log.append((self.n, 'start', v))
        wet = np.zeros(BLOCK)
        for voice in self.voices:
            if voice:
                wet += voice.block(self.n)
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


def oscillate_f32(freqs, blocks, phase=0):
    """The kernel's sines in float32: each (c, s) turned by (cos w, sin w) every sample, its size set back to 1 at the
    end of every block by x (1.5 - 0.5 (c^2 + s^2)). Returns c + i s at the end of each block, (blocks, len(freqs))."""
    f32 = np.float32
    w = 2.0 * np.pi * np.asarray(freqs, dtype=float) / FS
    C, S = np.cos(w).astype(f32), np.sin(w).astype(f32)
    c0, s0 = cos_sin(phase)
    c, s = np.full(len(w), c0, dtype=f32), np.full(len(w), s0, dtype=f32)
    half, three_halves = f32(0.5), f32(1.5)
    out = np.empty((blocks, len(w)), dtype=complex)
    for n in range(blocks):
        for _ in range(BLOCK):
            c, s = c * C - s * S, s * C + c * S
        k = three_halves - half * (c * c + s * s)
        c, s = c * k, s * k
        out[n] = c + 1j * s.astype(float)
    return out
