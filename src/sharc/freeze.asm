// freeze.asm - the freeze block's kernel; tools/sharc/freeze.py is its reference.
//
// This part is a grab's analysis. Each step runs one slice of its work a call (R4 = the slice), so that the kernel can
// spread the analysis over its blocks. FZ_RE and FZ_IM hold the 1,024 complex points' real and imaginary parts.
//   FZ_TABLES  R4 = 0..TABLE_SLICES-1   FZ_TAB, cos(2 pi (m - 512) / 2048) for m = 0..1535 (so cos t = FZ_TAB[t + 512]
//                                       and sin t = FZ_TAB[t] for t = 0..1023 in 2,048ths of a turn), then the
//                                       decimator's taps FZ_TAPS, scaled last to sum 1. Once, before any grab
//   FZ_ZERO                             the work area to 0
//   FZ_LOAD    R4 = 0..LOAD_SLICES-1    capture samples 2n and 2n + 1 (R5: the address of sample 2 LOAD_N R4; samples
//                                       before R7 read as 0) times a Hann window, as the complex point
//                                       z[n] = x[2n] + i x[2n+1] at its bit-reversed place. LOAD_N = 2^LOAD_SHIFT
//                                       points a slice
//   FZ_FFT     R4 = 0..                 a complex 1,024-point FFT in place: radix 2, decimation in time, stage by
//                                       stage. Stages 0-4 go twiddle by twiddle (its groups inner), stages 5-9 group
//                                       by group (its twiddles inner). FFT_N = 2^FFT_SHIFT butterflies a slice
//   FZ_SPLIT   R4 = 0..                 the real 2,048-point spectrum's power |X[k]|^2 for k = K_LO..NC - K_LO, at
//                                       FZ_RE + k: X[k] and X[NC - k] from Z[k] and Z[NC - k]. SPLIT_N = 2^SPLIT_SHIFT
//                                       pairs a slice
// They change R0-R15, I4-I7, I12-I15, M0, M3, M4, M8, M11, M12 and M13, and need L4-L7 and L12-L15 = 0.

.equ NC,           1024                 // complex points
.equ HALF_CAP,     750                  // points with samples: CAPTURE / 2
.equ TAB_SHIFT,    5                    // 32 entries of FZ_TAB a slice: 48 slices
.equ TAB_SLICES,   1536 >> TAB_SHIFT
.equ TAP_SHIFT,    4                    // 16 taps a slice, n = 1..63 from the middle out: 4 slices, then the sum
.equ TAP_SLICES,   (63 + (1 << TAP_SHIFT) - 1) >> TAP_SHIFT
.equ TABLE_SLICES, TAB_SLICES + TAP_SLICES + 1
.equ LOAD_SHIFT,   4                    // LOAD_N = 16 points a slice: 47 slices
.equ LOAD_SLICES,  (HALF_CAP + (1 << LOAD_SHIFT) - 1) >> LOAD_SHIFT
.equ FFT_SHIFT,    7                    // FFT_N = 128 butterflies a slice: 40 slices
.equ SPLIT_SHIFT,  6                    // SPLIT_N = 64 pairs a slice: 8 slices
.equ K_LO,         19                   // the lowest bin the grab looks at, less 1
.equ K_END,        513                  // pairs k = K_LO..512
.equ LATE,         5                    // the first stage that goes group by group

.section dm FZ_DM_BASE
FZ_REV5:  .word 0, 16, 8, 24, 4, 20, 12, 28, 2, 18, 10, 26, 6, 22, 14, 30     // 5-bit numbers reversed
          .word 1, 17, 9, 25, 5, 21, 13, 29, 3, 19, 11, 27, 7, 23, 15, 31
FZ_ROT:   .float 0.9999912153221553, 0.004191572320602106   // cos and sin of 2 pi / 1499: the window's step

.section dm FZ_DM_BASE+34              // zeros at boot: one zero-fill block in the boot stream
FZ_STATE: .space 8                     // FZ_FFT's loop counts around its butterflies, which use every data register
FZ_TAB:   .space 1536
FZ_TAPS:  .space 127
FZ_RE:    .space 1024
FZ_IM:    .space 1024

.section pm FZ_PM_BASE

// ---- FZ_TABLES: R4 = the slice.

FZ_TABLES:
    R0 = TAB_SLICES;
    R12 = R4 - R0;
    IF GE JUMP tb_taps;
    R12 = LSHIFT R4 BY TAB_SHIFT;       // m
    R0 = FZ_TAB;
    R0 = R0 + R12;
    I4 = R0;
    M4 = 1;
    R13 = 512;
    F14 = 0.00048828125;                // 1 / 2048
    R0 = 1;
    R0 = LSHIFT R0 BY TAB_SHIFT;
    LCNTR = R0, DO tb_c UNTIL LCE;
        R0 = R12 - R13;
        F0 = FLOAT R0;
        F0 = F0 * F14;
        CALL fz_cos;
        R12 = R12 + 1;
        NOP;                            // (no CALL in a loop's last three instructions)
tb_c:   DM(I4, M4) = F0;
    RTS;

tb_taps:                                // R12 = the slice among the taps': n = 1 + TAP_N R12 on, h[63 + n] = h[63 - n]
    R0 = TAP_SLICES;
    COMP(R12, R0);
    IF GE JUMP tb_sum;
    F0 = 1.0;
    DM(FZ_TAPS + 63) = F0;
    R6 = LSHIFT R12 BY TAP_SHIFT;
    R6 = R6 + 1;                        // n
    R0 = 1;
    R0 = LSHIFT R0 BY TAP_SHIFT;
    R0 = R6 + R0;
    R13 = 64;
    R13 = MIN(R0, R13);
    R13 = R13 - R6;                     // taps in the slice
    R0 = FZ_TAPS + 63;
    R1 = R0 + R6;
    I4 = R1;
    R1 = R0 - R6;
    I5 = R1;
    M4 = 1;
    M3 = -1;
    F14 = 0.057291666666666664;         // CUT / FS: the sinc is sin(2 pi CUT n / FS) / (2 pi CUT n / FS)
    F15 = 0.007936507936507936;         // 1 / 126: the Hamming window is 0.54 + 0.46 cos(2 pi n / 126)
    LCNTR = R13, DO tb_t UNTIL LCE;
        F12 = FLOAT R6;
        F0 = F12 * F15;
        CALL fz_cos;
        F13 = 0.46;
        F0 = F0 * F13;
        F13 = 0.54;
        F2 = F0 + F13;
        F0 = F12 * F14;
        F13 = 0.25;
        F0 = F0 - F13;
        CALL fz_cos;
        F3 = PASS F0;
        F0 = F12 * F14;
        F13 = 6.283185307179586;
        F0 = F0 * F13;
        CALL fz_recip;
        F0 = F0 * F3;
        F0 = F0 * F2;
        DM(I4, M4) = F0;
        R6 = R6 + 1;
tb_t:   DM(I5, M3) = F0;
    RTS;

tb_sum:                                 // the taps over their sum
    I4 = FZ_TAPS;
    M4 = 1;
    F0 = 0.0;
    F1 = DM(I4, M4);
    LCNTR = 126, DO tb_s UNTIL LCE;
tb_s:   F0 = F0 + F1, F1 = DM(I4, M4);
    F0 = F0 + F1;
    CALL fz_recip;
    I4 = FZ_TAPS;
    I5 = FZ_TAPS;
    LCNTR = 127, DO tb_n UNTIL LCE;
        F1 = DM(I4, M4);
        F1 = F1 * F0;
tb_n:   DM(I5, M4) = F1;
    RTS;


// ---- FZ_ZERO

FZ_ZERO:
    I4 = FZ_RE;
    I12 = FZ_IM;
    M4 = 1;
    M12 = 1;
    R0 = 0;
    LCNTR = NC, DO zr UNTIL LCE;
zr:     DM(I4, M4) = R0, PM(I12, M12) = R0;
    RTS;


// ---- FZ_LOAD: R4 = the slice, R5 = the address of its first sample, R7 = the first sample written. Point n has
// samples 2n and 2n + 1 (DM through I4); the window is 0.5 - 0.5 c, with (c, s) = (cos, sin) 2 pi m / 1499 from the
// slice's first sample m, turned 2 pi / 1499 a sample and set back to size 1 a point.

FZ_LOAD:
    R6 = LSHIFT R4 BY LOAD_SHIFT;       // n, the slice's first point
    R0 = 1;
    R0 = LSHIFT R0 BY LOAD_SHIFT;
    R0 = R6 + R0;
    R1 = HALF_CAP;
    R0 = MIN(R0, R1);
    R2 = R0 - R6;                       // points in the slice
    I4 = R5;
    M4 = 1;
    R0 = LSHIFT R6 BY 1;
    F0 = FLOAT R0;
    F1 = 0.0006671114076050700;         // 1 / 1499
    F3 = F0 * F1;                       // the slice's first sample, in turns
    F0 = PASS F3;
    CALL fz_cos;
    F4 = PASS F0;
    F0 = 0.25;
    F0 = F3 - F0;
    CALL fz_cos;
    F10 = PASS F4;                      // c
    F11 = PASS F0;                      // s
    F12 = DM(FZ_ROT);
    F13 = DM(FZ_ROT + 1);
    F14 = 0.5;
    F15 = 1.5;
    LCNTR = R2, DO ld_pt UNTIL LCE;
        R8 = 31;
        R8 = R6 AND R8;
        I5 = R8;
        R8 = LSHIFT R6 BY -5;
        I7 = R8;
        R8 = DM(FZ_REV5, I5);
        R9 = DM(FZ_REV5, I7);
        R8 = LSHIFT R8 BY 5;
        R8 = R8 + R9;
        I5 = R8;                        // rev10(n) = 32 rev5(n & 31) + rev5(n >> 5)
        R0 = DM(I4, M4);
        R1 = DM(I4, M4);
        R8 = LSHIFT R6 BY 1;
        COMP(R8, R7);
        IF LT R0 = R0 - R0;             // not written yet: 0 (whatever the word holds)
        R8 = R8 + 1;
        COMP(R8, R7);
        IF LT R1 = R1 - R1;
        F2 = F10 * F14;
        F4 = F14 - F2;                  // sample 2n's window
        F2 = F10 * F12;
        F3 = F11 * F13;
        F8 = F10 * F13;
        F9 = F11 * F12;
        F10 = F2 - F3;
        F11 = F9 + F8;
        F2 = F10 * F14;
        F5 = F14 - F2;                  // sample 2n + 1's
        F2 = F10 * F12;
        F3 = F11 * F13;
        F8 = F10 * F13;
        F9 = F11 * F12;
        F10 = F2 - F3;
        F11 = F9 + F8;
        F2 = F10 * F10;
        F3 = F11 * F11;
        F2 = F2 + F3;
        F2 = F2 * F14;
        F2 = F15 - F2;
        F10 = F10 * F2;
        F11 = F11 * F2;
        F0 = F0 * F4;
        F1 = F1 * F5;
        DM(FZ_RE, I5) = F0;
        DM(FZ_IM, I5) = F1;
ld_pt:  R6 = R6 + 1;
    RTS;


// ---- FZ_FFT: R4 = the slice. Stage s pairs points a and a + h, h = 2^s, a = 2h g + j for group g and twiddle j < h,
// with W = e^(-2 pi i j / 2h) = cos t - i sin t, t = j 2^(10 - s) in FZ_TAB's steps.
// A butterfly reads a and b = a + h without moving (M0, M8 = 0) and writes a + Wb, a - Wb moving on (M4, M12):
// W b = (br c + bi s) + i (bi c - br s), with F4 = c and F5 = s.

FZ_FFT:
    M0 = 0;
    M8 = 0;
    R7 = LSHIFT R4 BY FFT_SHIFT;        // the slice's first butterfly in all
    R6 = LSHIFT R7 BY -9;               // s
    R0 = 511;
    R7 = R7 AND R0;                     // n in the stage
    R0 = 1;
    R8 = LSHIFT R0 BY R6;               // h
    R12 = 1;
    R12 = LSHIFT R12 BY FFT_SHIFT;      // butterflies left in the slice
    R13 = 10;
    R13 = R13 - R6;                     // t = j << (10 - s)
    R14 = 1;
    R14 = R6 + R14;                     // 2h g = g << (s + 1)
    R0 = LATE;
    COMP(R6, R0);
    IF GE JUMP fl;

// stages 0-4: butterfly n is twiddle j = n >> (9 - s) of group g = n & (G - 1), G = 512 >> s groups, 2h points apart
    R0 = 9;
    R0 = R6 - R0;
    R10 = LSHIFT R7 BY R0;              // j
    R0 = -R6;
    R9 = 512;
    R9 = LSHIFT R9 BY R0;               // G
    R0 = 1;
    R11 = R9 - R0;
    R11 = R7 AND R11;                   // g
    R0 = LSHIFT R8 BY 1;
    M4 = R0;
    M12 = R0;
fe_j:
    R0 = LSHIFT R10 BY R13;             // t
    R1 = FZ_TAB;
    R1 = R0 + R1;
    I6 = R1;
    F5 = DM(0, I6);
    F4 = DM(512, I6);
    R0 = LSHIFT R11 BY R14;
    R0 = R0 + R10;                      // a
    CALL fft_points;
    R0 = R9 - R11;                      // this twiddle's groups left, as many as the slice has
    R0 = MIN(R0, R12);
    R12 = R12 - R0;
    DM(FZ_STATE) = R8;
    DM(FZ_STATE + 1) = R9;
    DM(FZ_STATE + 2) = R10;
    DM(FZ_STATE + 3) = R12;
    DM(FZ_STATE + 4) = R13;
    DM(FZ_STATE + 5) = R14;
    LCNTR = R0, DO fe_b UNTIL LCE;
        F8 = DM(I4, M0), F0 = PM(I12, M8);
        F10 = F0 * F4, F9 = DM(I5, M0), F1 = PM(I13, M8);
        F12 = F1 * F5;
        F11 = F1 * F4, F14 = F10 + F12;
        F13 = F0 * F5;
        F15 = F11 - F13;
        F2 = F8 + F14, F3 = F8 - F14;
        F6 = F9 + F15, F7 = F9 - F15, DM(I4, M4) = F2, PM(I12, M12) = F3;
fe_b:   DM(I5, M4) = F6, PM(I13, M12) = F7;
    R8 = DM(FZ_STATE);
    R9 = DM(FZ_STATE + 1);
    R10 = DM(FZ_STATE + 2);
    R12 = DM(FZ_STATE + 3);
    R13 = DM(FZ_STATE + 4);
    R14 = DM(FZ_STATE + 5);
    R12 = PASS R12;
    IF EQ RTS;
    R11 = 0;
    R10 = R10 + 1;
    JUMP fe_j;

// stages 5-9: butterfly n is twiddle j = n & (h - 1) of group g = n >> s; the twiddles stream from FZ_TAB T = 2^(10 - s)
// steps apart, the cos up from t + 512 (I6) and the sin up from t (I14)
fl:
    R0 = -R6;
    R10 = LSHIFT R7 BY R0;              // g
    R0 = 1;
    R11 = R8 - R0;
    R11 = R7 AND R11;                   // j
    R0 = 1;
    R15 = LSHIFT R0 BY R13;             // T
    M3 = R15;
    M11 = R15;
    M4 = 1;
    M12 = 1;
fl_g:
    R9 = R11 + R12;
    R9 = MIN(R9, R8);                   // this group's last twiddle + 1, as many as the slice has
    R2 = R9 - R11;
    R12 = R12 - R2;
    R0 = LSHIFT R10 BY R14;
    R0 = R0 + R11;                      // a
    CALL fft_points;
    R0 = LSHIFT R11 BY R13;             // t
    R1 = FZ_TAB;
    R1 = R1 + R0;
    I14 = R1;
    R0 = 512;
    R1 = R1 + R0;
    I6 = R1;
    DM(FZ_STATE) = R8;
    DM(FZ_STATE + 1) = R10;
    DM(FZ_STATE + 2) = R12;
    DM(FZ_STATE + 3) = R13;
    DM(FZ_STATE + 4) = R14;
    F4 = DM(I6, M3), F5 = PM(I14, M11);
    LCNTR = R2, DO fl_a UNTIL LCE;
        F8 = DM(I4, M0), F0 = PM(I12, M8);
        F10 = F0 * F4, F9 = DM(I5, M0), F1 = PM(I13, M8);
        F12 = F1 * F5;
        F11 = F1 * F4, F14 = F10 + F12;
        F13 = F0 * F5;
        F15 = F11 - F13, F4 = DM(I6, M3), F5 = PM(I14, M11);
        F2 = F8 + F14, F3 = F8 - F14;
        F6 = F9 + F15, F7 = F9 - F15, DM(I4, M4) = F2, PM(I12, M12) = F3;
fl_a:   DM(I5, M4) = F6, PM(I13, M12) = F7;
    R8 = DM(FZ_STATE);
    R10 = DM(FZ_STATE + 1);
    R12 = DM(FZ_STATE + 2);
    R13 = DM(FZ_STATE + 3);
    R14 = DM(FZ_STATE + 4);
    R12 = PASS R12;
    IF EQ RTS;
    R11 = 0;
    R10 = R10 + 1;
    JUMP fl_g;

fft_points:                             // R0 = a: I4, I5 at its real and imaginary parts, I12, I13 at b = a + h's
    R1 = FZ_RE;
    R1 = R0 + R1;
    I4 = R1;
    R1 = R1 + R8;
    I12 = R1;
    R1 = FZ_IM;
    R1 = R0 + R1;
    I5 = R1;
    R1 = R1 + R8;
    I13 = R1;
    RTS;


// ---- FZ_SPLIT: R4 = the slice. With A = Z[k], B = Z[NC - k], E = A + B*, O = (A - B*)/i and
// T = O e^(-2 pi i k / 2048): X[k] = (E + T)/2 and X[NC - k] = ((E - T)/2)*. A's and B's real parts are read in place
// (M0) and their powers written there; the imaginary parts through I12 and I13, the cos up through I6 and the sin up
// through I14.

FZ_SPLIT:
    R6 = LSHIFT R4 BY SPLIT_SHIFT;
    R0 = K_LO;
    R6 = R6 + R0;                       // k
    R7 = 1;
    R7 = LSHIFT R7 BY SPLIT_SHIFT;
    R7 = R6 + R7;
    R0 = K_END;
    R7 = MIN(R7, R0);
    R7 = R7 - R6;                       // pairs in this slice
    R1 = FZ_RE;
    R0 = R6 + R1;
    I4 = R0;                            // A
    R1 = NC;
    R0 = R0 + R1;
    I12 = R0;
    R1 = FZ_RE + NC;
    R0 = R1 - R6;
    I5 = R0;                            // B
    I15 = R0;
    R1 = NC;
    R0 = R0 + R1;
    I13 = R0;
    R1 = FZ_TAB;
    R0 = R6 + R1;
    I14 = R0;                           // sin at k
    R1 = 512;
    R0 = R0 + R1;
    I6 = R0;                            // cos at k
    M0 = 0;
    M3 = -1;
    M4 = 1;
    M12 = 1;
    M13 = -1;
    F14 = 0.25;
    LCNTR = R7, DO sp_k UNTIL LCE;
        F8 = DM(I4, M0), F9 = PM(I12, M12);                            // ar, ai
        F10 = DM(I5, M3), F11 = PM(I13, M13);                          // br, bi
        F2 = F8 + F10, F3 = F8 - F10, F4 = DM(I6, M4), F5 = PM(I14, M12);  // E re, -O im; cos, sin
        F6 = F9 + F11, F7 = F9 - F11;                                  // O re, E im
        F12 = F6 * F4;
        F13 = F3 * F5;
        F0 = F3 * F4;
        F1 = F6 * F5;
        F12 = F12 - F13;                                               // T re
        F13 = F0 + F1;                                                 // -T im
        F8 = F2 + F12, F9 = F2 - F12;
        F11 = F7 + F13, F10 = F7 - F13;
        F8 = F8 * F8;
        F10 = F10 * F10;
        F8 = F8 + F10;
        F9 = F9 * F9;
        F11 = F11 * F11;
        F9 = F9 + F11;
        F8 = F8 * F14;
        F9 = F9 * F14;
sp_k:   DM(I4, M4) = F8, PM(I15, M13) = F9;
    RTS;


// ---- the arithmetic the steps share

// fz_cos: F0 = t, a phase in turns (any sign, |t| < 2^23): F0 = cos 2 pi t, within 1e-7. t folds to u in
// [-1/4, 1/4] with cos 2 pi t = sin 2 pi u, and sin x is its series to x^13. Changes R1 and F8-F11.
fz_cos:
    F8 = ABS F0;
    R1 = TRUNC F8;
    F9 = FLOAT R1;
    F8 = F8 - F9;                       // the turn's fraction
    F9 = 1.0;
    F9 = F9 - F8;
    F8 = MIN(F8, F9);                   // 0 .. 1/2
    F9 = 0.25;
    F8 = F9 - F8;                       // u
    F9 = 6.283185307179586;
    F8 = F8 * F9;                       // x
    F9 = F8 * F8;
    F10 = 1.6059043836821613e-10;       // 1/13!
    F11 = -2.505210838544172e-08;
    F10 = F10 * F9;
    F10 = F10 + F11;
    F11 = 2.755731922398589e-06;
    F10 = F10 * F9;
    F10 = F10 + F11;
    F11 = -0.0001984126984126984;
    F10 = F10 * F9;
    F10 = F10 + F11;
    F11 = 0.008333333333333333;
    F10 = F10 * F9;
    F10 = F10 + F11;
    F11 = -0.16666666666666666;
    F10 = F10 * F9;
    F10 = F10 + F11;
    F11 = 1.0;
    F10 = F10 * F9;
    F10 = F10 + F11;
    F0 = F10 * F8;
    RTS;

// fz_recip: F0 = 1 / F0 (F0 not 0): RECIPS's seed and two Newton steps. Changes F1, F8 and F9.
fz_recip:
    F8 = RECIPS F0;
    F9 = 2.0;
    F1 = F0 * F8;
    F1 = F9 - F1;
    F8 = F8 * F1;
    F1 = F0 * F8;
    F1 = F9 - F1;
    F0 = F8 * F1;
    RTS;
