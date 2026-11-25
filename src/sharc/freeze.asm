// freeze.asm - the freeze block's kernel; tools/sharc/freeze.py is its reference.
//
// This part is a grab's analysis. Each step runs one slice of its work a call (R4 = the slice), so that the kernel can
// spread the analysis over its blocks. FZ_RE and FZ_IM hold the 1,024 complex points' real and imaginary parts.
//   FZ_TABLES            cos(2 pi k / 2048) for k = 0..512 into FZ_COS (the twiddles, read a quarter turn at a time),
//                        and the Hann window's first half into FZ_HANN
//   FZ_LOAD   R4 = 0..   the capture (R5: the address of its first of CAPTURE samples) times a Hann window, as complex
//                        points z[n] = x[2n] + i x[2n+1] at their bit-reversed places; zeros from sample CAPTURE on.
//                        LOAD_N = 2^LOAD_SHIFT points a slice
//   FZ_FFT    R4 = 0..   a complex 1,024-point FFT in place: radix 2, decimation in time, stage by stage. Stages 0-4 go
//                        twiddle by twiddle (its groups inner), stages 5-9 group by group (its twiddles inner).
//                        FFT_N = 2^FFT_SHIFT butterflies a slice
//   FZ_SPLIT  R4 = 0..   the real 2,048-point spectrum's power |X[k]|^2 for k = K_LO..NC - K_LO, at FZ_RE + k:
//                        X[k] and X[NC - k] from Z[k] and Z[NC - k]. SPLIT_N = 2^SPLIT_SHIFT pairs a slice
// They change R0-R15, I4-I7, I12-I15, M0, M3, M4, M8, M11, M12 and M13, and need L4-L7 and L12-L15 = 0.

.equ NC,          1024                  // complex points
.equ CAPTURE,     1500                  // samples a grab analyses
.equ HALF_CAP,    750                   // points with samples
.equ LOAD_SHIFT,  6                     // LOAD_N = 64 points a slice: 16 slices
.equ FFT_SHIFT,   7                     // FFT_N = 128 butterflies a slice: 40 slices
.equ SPLIT_SHIFT, 6                     // SPLIT_N = 64 pairs a slice: 8 slices
.equ K_LO,        19                    // the lowest bin the grab looks at, less 1
.equ K_END,       513                   // pairs k = K_LO..512
.equ LATE,        5                     // the first stage that goes group by group

.section dm FZ_DM_BASE
FZ_REV5:  .word 0, 16, 8, 24, 4, 20, 12, 28, 2, 18, 10, 26, 6, 22, 14, 30     // 5-bit numbers reversed
          .word 1, 17, 9, 25, 5, 21, 13, 29, 3, 19, 11, 27, 7, 23, 15, 31
FZ_ROT:   .float 0.9999912153221553, 0.004191572320602106   // cos and sin of 2 pi / (CAPTURE - 1): the window's step

.section dm FZ_DM_BASE+34              // zeros at boot: one zero-fill block in the boot stream
FZ_STATE: .space 8                     // FZ_FFT's loop counts around its butterflies, which use every data register
FZ_HANN:  .space 750                   // 0.5 - 0.5 cos(2 pi m / (CAPTURE - 1)), m = 0..749: the rest mirrors it
FZ_COS:   .space 513
FZ_RE:    .space 1024
FZ_IM:    .space 1024

.section pm FZ_PM_BASE

FZ_TABLES:
    I4 = FZ_COS;
    M4 = 1;
    R12 = 0;
    R13 = 1;
    F14 = 0.0030679615757712823;        // 2 pi / 2048
    LCNTR = 513, DO tab UNTIL LCE;      // cos x by its series to x^12 (error under 1e-8 up to pi / 2)
        F8 = FLOAT R12;
        F8 = F8 * F14;
        F9 = F8 * F8;
        F10 = 2.08767569878681e-09;
        F11 = -2.755731922398589e-07;
        F10 = F10 * F9;
        F10 = F10 + F11;
        F11 = 2.48015873015873e-05;
        F10 = F10 * F9;
        F10 = F10 + F11;
        F11 = -0.001388888888888889;
        F10 = F10 * F9;
        F10 = F10 + F11;
        F11 = 0.041666666666666664;
        F10 = F10 * F9;
        F10 = F10 + F11;
        F11 = -0.5;
        F10 = F10 * F9;
        F10 = F10 + F11;
        F11 = 1.0;
        F10 = F10 * F9;
        F10 = F10 + F11;
        DM(I4, M4) = F10;
tab:    R12 = R12 + R13;
    I4 = FZ_HANN;                       // the window: (c, s) turned 2 pi / (CAPTURE - 1) a sample, set back to size 1
    F12 = DM(FZ_ROT);
    F13 = DM(FZ_ROT + 1);
    F14 = 0.5;
    F15 = 1.5;
    F8 = 1.0;
    F9 = 0.0;
    LCNTR = HALF_CAP, DO hann UNTIL LCE;
        F0 = F8 * F14;
        F0 = F14 - F0;
        DM(I4, M4) = F0;
        F4 = F8 * F12;
        F5 = F9 * F13;
        F10 = F8 * F13;
        F11 = F9 * F12;
        F8 = F4 - F5;
        F9 = F11 + F10;
        F4 = F8 * F8;
        F5 = F9 * F9;
        F4 = F4 + F5;
        F4 = F4 * F14;
        F4 = F15 - F4;
        F8 = F8 * F4;
hann:   F9 = F9 * F4;
    RTS;


// ---- FZ_LOAD: R4 = the slice, R5 = the capture's address. Point n has samples 2n (DM through I4) and 2n + 1 (PM
// through I12), and their window values at FZ_HANN + 2n and 2n + 1 below the middle (n < CAPTURE / 4), mirrored at
// FZ_HANN + 1499 - 2n and 1498 - 2n above it.

FZ_LOAD:
    M4 = 2;
    M12 = 2;
    R6 = LSHIFT R4 BY LOAD_SHIFT;       // n, the slice's first point
    R7 = 1;
    R7 = LSHIFT R7 BY LOAD_SHIFT;
    R7 = R6 + R7;                       // and its end
    R0 = LSHIFT R6 BY 1;
    R0 = R0 + R5;
    I4 = R0;
    R1 = 1;
    R0 = R0 + R1;
    I12 = R0;
    R2 = FZ_REV5;
    R3 = FZ_RE;
    R1 = CAPTURE / 4;                   // points below the middle
    R0 = MIN(R7, R1);
    R0 = R0 - R6;
    R0 = PASS R0;
    IF LE JUMP ld_up;
    R1 = LSHIFT R6 BY 1;
    R8 = FZ_HANN;
    R1 = R1 + R8;
    I6 = R1;
    R8 = 1;
    R1 = R1 + R8;
    I14 = R1;
    M3 = 2;
    M13 = 2;
    CALL ld_run;
ld_up:
    R1 = CAPTURE / 4;
    R0 = MAX(R6, R1);
    R1 = HALF_CAP;
    R8 = MIN(R7, R1);
    R8 = R8 - R0;                       // points above the middle with samples
    R8 = PASS R8;
    IF LE JUMP ld_zero;
    R1 = R6;
    R6 = R0;                            // (from the middle if the slice starts below it)
    R0 = LSHIFT R6 BY 1;
    R9 = FZ_HANN + CAPTURE - 1;
    R9 = R9 - R0;
    I6 = R9;
    R10 = 1;
    R9 = R9 - R10;
    I14 = R9;
    M3 = -2;
    M13 = -2;
    R0 = R8;
    CALL ld_run;
ld_zero:
    R0 = HALF_CAP;
    R0 = MAX(R6, R0);
    R6 = R0;
    R0 = R7 - R6;                       // points past the samples
    R0 = PASS R0;
    IF LE RTS;
    R11 = 0;
    LCNTR = R0, DO ld_z UNTIL LCE;
        R10 = 31;
        R10 = R6 AND R10;
        R10 = R10 + R2;
        I5 = R10;
        R10 = LSHIFT R6 BY -5;
        R10 = R10 + R2;
        I7 = R10;
        R10 = DM(0, I5);
        R12 = DM(0, I7);
        R10 = LSHIFT R10 BY 5;
        R10 = R10 + R12;
        R10 = R10 + R3;
        I5 = R10;
        DM(0, I5) = R11;
        DM(NC, I5) = R11;
        R12 = 1;
ld_z:   R6 = R6 + R12;
    RTS;

ld_run:                                 // R0 points from n: the samples times the window at bit-reversed places
    R13 = 1;
    LCNTR = R0, DO ld_pt UNTIL LCE;
        R10 = 31;
        R10 = R6 AND R10;
        R10 = R10 + R2;
        I5 = R10;
        R10 = LSHIFT R6 BY -5;
        R10 = R10 + R2;
        I7 = R10;
        R10 = DM(0, I5);
        R12 = DM(0, I7);
        R10 = LSHIFT R10 BY 5;
        R10 = R10 + R12;
        R10 = R10 + R3;
        I5 = R10;                       // FZ_RE + rev10(n): 32 rev5(n & 31) + rev5(n >> 5)
        F0 = DM(I4, M4), F1 = PM(I12, M12);
        F4 = DM(I6, M3), F5 = PM(I14, M13);
        F0 = F0 * F4;
        F1 = F1 * F5;
        DM(0, I5) = F0;
        DM(NC, I5) = F1;
ld_pt:  R6 = R6 + R13;
    RTS;


// ---- FZ_FFT: R4 = the slice. Stage s pairs points a and a + h, h = 2^s, a = 2h g + j for group g and twiddle j < h,
// with W = e^(-2 pi i j / 2h) = cos t - i sin t, t = j 2^(10 - s) in FZ_COS's steps (cos t = -cos(1024 - t) past 512).
// A butterfly reads a and b = a + h without moving (M0, M8 = 0) and writes a + Wb, a - Wb moving on (M4, M12).

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
    R1 = 512;
    R2 = FZ_COS;
    COMP(R0, R1);
    IF GT JUMP fe_hi;
    R3 = R0 + R2;                       // t <= 512: W = q[t] - i q[512 - t]
    I6 = R3;
    F4 = DM(0, I6);
    R3 = R1 - R0;
    R3 = R3 + R2;
    I6 = R3;
    F5 = DM(0, I6);
    F5 = -F5;
    JUMP fe_w;
fe_hi:
    R3 = 1024;                          // t > 512: W = -q[1024 - t] - i q[t - 512]
    R3 = R3 - R0;
    R3 = R3 + R2;
    I6 = R3;
    F4 = DM(0, I6);
    F4 = -F4;
    R3 = R0 - R1;
    R3 = R3 + R2;
    I6 = R3;
    F5 = DM(0, I6);
    F5 = -F5;
fe_w:
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
    LCNTR = R0, DO fe_b UNTIL LCE;      // W b = (br wr - bi wi) + i (bi wr + br wi), F4 = wr, F5 = wi
        F8 = DM(I4, M0), F0 = PM(I12, M8);
        F10 = F0 * F4, F9 = DM(I5, M0), F1 = PM(I13, M8);
        F12 = F1 * F5;
        F11 = F1 * F4, F14 = F10 - F12;
        F13 = F0 * F5;
        F15 = F11 + F13;
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
    R0 = 1;
    R10 = R10 + R0;
    JUMP fe_j;

// stages 5-9: butterfly n is twiddle j = n & (h - 1) of group g = n >> s; the twiddles from FZ_COS T = 2^(10 - s)
// steps apart, a pass for j < h / 2 (W = c - i s, c up from q[t], s down from q[512 - t]) and one for the rest
// (W = -c - i s, c down from q[1024 - t], s up from q[t - 512]: a and b swap their sums)
fl:
    R0 = -R6;
    R10 = LSHIFT R7 BY R0;              // g
    R0 = 1;
    R11 = R8 - R0;
    R11 = R7 AND R11;                   // j
    R0 = 1;
    R15 = LSHIFT R0 BY R13;             // T
    M4 = 1;
    M12 = 1;
fl_g:
    R9 = R11 + R12;
    R9 = MIN(R9, R8);                   // this group's last twiddle + 1, as many as the slice has
    R0 = R9 - R11;
    R12 = R12 - R0;
    R1 = LSHIFT R8 BY -1;               // h / 2
    R2 = MIN(R9, R1);
    R2 = R2 - R11;                      // twiddles below h / 2
    R2 = PASS R2;
    IF LE JUMP fl_b;
    R0 = LSHIFT R10 BY R14;
    R0 = R0 + R11;                      // a
    CALL fft_points;
    R0 = LSHIFT R11 BY R13;             // t
    R3 = FZ_COS;
    R1 = R3 + R0;
    I6 = R1;
    M3 = R15;
    R1 = 512;
    R1 = R1 - R0;
    R1 = R1 + R3;
    I14 = R1;
    R1 = -R15;
    M11 = R1;
    CALL fl_save;
    F4 = DM(I6, M3), F5 = PM(I14, M11);
    LCNTR = R2, DO fl_a UNTIL LCE;      // W b = (br c + bi s) + i (bi c - br s)
        F8 = DM(I4, M0), F0 = PM(I12, M8);
        F10 = F0 * F4, F9 = DM(I5, M0), F1 = PM(I13, M8);
        F12 = F1 * F5;
        F11 = F1 * F4, F14 = F10 + F12;
        F13 = F0 * F5;
        F15 = F11 - F13, F4 = DM(I6, M3), F5 = PM(I14, M11);
        F2 = F8 + F14, F3 = F8 - F14;
        F6 = F9 + F15, F7 = F9 - F15, DM(I4, M4) = F2, PM(I12, M12) = F3;
fl_a:   DM(I5, M4) = F6, PM(I13, M12) = F7;
    CALL fl_load;
fl_b:
    R1 = LSHIFT R8 BY -1;
    R0 = MAX(R11, R1);                  // the first twiddle from h / 2
    R2 = R9 - R0;
    R2 = PASS R2;
    IF LE JUMP fl_next;
    R11 = R0;
    R0 = LSHIFT R10 BY R14;
    R0 = R0 + R11;                      // a
    CALL fft_points;
    R0 = LSHIFT R11 BY R13;             // t
    R3 = FZ_COS;
    R1 = 1024;
    R1 = R1 - R0;
    R1 = R1 + R3;
    I6 = R1;
    R1 = -R15;
    M3 = R1;
    R1 = 512;
    R1 = R0 - R1;
    R1 = R1 + R3;
    I14 = R1;
    M11 = R15;
    CALL fl_save;
    F4 = DM(I6, M3), F5 = PM(I14, M11);
    LCNTR = R2, DO fl_bb UNTIL LCE;     // -W b = (br c - bi s) + i (bi c + br s): a takes the difference
        F8 = DM(I4, M0), F0 = PM(I12, M8);
        F10 = F0 * F4, F9 = DM(I5, M0), F1 = PM(I13, M8);
        F12 = F1 * F5;
        F11 = F1 * F4, F14 = F10 - F12;
        F13 = F0 * F5;
        F15 = F11 + F13, F4 = DM(I6, M3), F5 = PM(I14, M11);
        F2 = F8 + F14, F3 = F8 - F14;
        F6 = F9 + F15, F7 = F9 - F15, DM(I4, M4) = F3, PM(I12, M12) = F2;
fl_bb:  DM(I5, M4) = F7, PM(I13, M12) = F6;
    CALL fl_load;
fl_next:
    R12 = PASS R12;
    IF EQ RTS;
    R11 = 0;
    R0 = 1;
    R10 = R10 + R0;
    JUMP fl_g;

fl_save:
    DM(FZ_STATE) = R8;
    DM(FZ_STATE + 1) = R9;
    DM(FZ_STATE + 2) = R10;
    DM(FZ_STATE + 3) = R11;
    DM(FZ_STATE + 4) = R12;
    DM(FZ_STATE + 5) = R13;
    DM(FZ_STATE + 6) = R14;
    DM(FZ_STATE + 7) = R15;
    RTS;

fl_load:
    R8 = DM(FZ_STATE);
    R9 = DM(FZ_STATE + 1);
    R10 = DM(FZ_STATE + 2);
    R11 = DM(FZ_STATE + 3);
    R12 = DM(FZ_STATE + 4);
    R13 = DM(FZ_STATE + 5);
    R14 = DM(FZ_STATE + 6);
    R15 = DM(FZ_STATE + 7);
    RTS;

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
// (M0) and their powers written there; the imaginary parts through I12 and I13, the cos up through I6 and the sin down
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
    R1 = FZ_COS;
    R0 = R6 + R1;
    I6 = R0;                            // cos at k
    R1 = FZ_COS + 512;
    R0 = R1 - R6;
    I14 = R0;                           // sin at k
    M0 = 0;
    M3 = -1;
    M4 = 1;
    M12 = 1;
    M13 = -1;
    F14 = 0.25;
    LCNTR = R7, DO sp_k UNTIL LCE;
        F8 = DM(I4, M0), F9 = PM(I12, M12);                            // ar, ai
        F10 = DM(I5, M3), F11 = PM(I13, M13);                          // br, bi
        F2 = F8 + F10, F3 = F8 - F10, F4 = DM(I6, M4), F5 = PM(I14, M13);  // E re, -O im; cos, sin
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
