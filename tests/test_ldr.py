"""Entry 2's LDR blocks: data that is all zeros goes in as a zero-fill (tag 1) block, as stock loads its own zeroed arrays."""
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import patch_amp as pa
import visa_dis as vd

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = {5: lambda c: ((c + 1) & ~1) * 3 // 2, 4: lambda c: c, 3: lambda c: (c + 1) // 2, 6: lambda c: c * 2,
           10: lambda c: c, 9: lambda c: c}


def blocks(e2_raw):
    """(tag, count, address, payload) of each block up to FINAL_INIT, from the 384-word header on."""
    w = struct.unpack('<%dI' % (len(e2_raw) // 4), e2_raw)
    i, out = 384, []
    while True:
        tag, cnt, addr = w[i:i + 3]
        if tag == 0:
            return out
        n = PAYLOAD.get(tag, lambda c: 0)(cnt)
        out.append((tag, cnt, addr, w[i + 3:i + 3 + n]))
        i += 3 + n


def entry2(hxf):
    data, _ = pa.load_l6ia_from_any(str(hxf))
    ent = pa.l6ia.parse(data)[2]
    return data[ent['payload_off']:ent['payload_off'] + ent['payload_len']]


def boot_kernel(hxf):
    """Entry 2's first 384 words, the boot kernel: 256 48-bit instructions at PM 0x8c000, as visa_dis text by address."""
    raw = entry2(hxf)[:384 * 4]
    return {0x8c000 + k: vd.isa_text(int.from_bytes(raw[6 * k:6 * k + 6], 'little'), 0x8c000 + k) for k in range(256)}


def handlers(code):
    """{tag: address of its code}, from the kernel's dispatch (R0 = PASS R8, then IF EQ JUMP and R0 = R0 - 1 in turn),
    through a plain JUMP that two tags share."""
    pc = next(a for a, t in code.items() if t == 'R0 = PASS R8') + 1
    out = {}
    while m := re.fullmatch(r'IF EQ JUMP (0x[0-9a-f]+)', code[pc]):
        to = int(m[1], 16)
        jump = re.fullmatch(r'JUMP (0x[0-9a-f]+)', code[to])
        out[len(out)] = int(jump[1], 16) if jump else to
        if code[pc + 1] != 'R0 = R0 - 1':
            break
        pc += 2
    return out


def test_all_zero_data_is_a_zero_fill_block():
    assert pa.pack_init_l32(0xc7ce0, [0] * 796) == [1, 796, 0xc7ce0]


def test_a_single_zero_word_is_a_zero_fill_block_too():
    assert pa.pack_init_l32(0xe4f0e, [0]) == [1, 1, 0xe4f0e]


def test_data_with_any_other_word_keeps_its_words():
    assert pa.pack_init_l32(0xe7c26, [0, 0, 0x3F7FEED8, 0]) == [4, 4, 0xe7c26, 0, 0, 0x3F7FEED8, 0]


def test_no_data_stays_an_empty_init_block():
    assert pa.pack_init_l32(0x1000, []) == [4, 0, 0x1000]


def test_new_blocks_go_before_final_init_past_a_zero_fill_block():
    e2 = [0] * 384 + [1, 796, 0xc7ce0] + [4, 1, 0x1000, 7] + [0, 0, 0] + [0] * 384
    raw = struct.pack('<%dI' % len(e2), *e2)
    out = pa.inject_sharc_ldr_blocks(raw, pa.pack_init_l32(0x2000, [0] * 8) + pa.pack_init_l32(0x3000, [5]))
    assert blocks(out) == [(1, 796, 0xc7ce0, ()), (4, 1, 0x1000, (7,)), (1, 8, 0x2000, ()), (4, 1, 0x3000, (5,))]


@pytest.mark.firmware
def test_the_build_loads_no_all_zero_init_block(tmp_path):
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    out = tmp_path / 'out.hxf'
    env = dict(os.environ, HX_GR='1', HX_CLICK='1', HX_FX_GATE='1', HX_USB_MONITOR='1', HX_GATE_SC='1')
    r = subprocess.run([sys.executable, str(ROOT / 'build.py'), stock, '-o', str(out), '--no-check'],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    stock_blocks = blocks(entry2(stock))
    ours = blocks(entry2(out))
    assert not [b for b in stock_blocks if b[0] == 4 and b[1] and not any(b[3])], 'stock itself had one'
    assert not [(hex(a), c) for t, c, a, p in ours if t == 4 and c and not any(p)]
    assert sum(t == 1 for t, *_ in ours) > sum(t == 1 for t, *_ in stock_blocks)


@pytest.mark.firmware
def test_the_boot_kernel_zero_fills_the_words_a_data_block_would_write():
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    code = boot_kernel(stock)
    run = lambda a, n: [code[a + k] for k in range(n)]
    tag = handlers(code)
    assert sorted(tag) == list(range(11)) and tag[0] == 0x8c07c
    assert tag[7] == tag[8] == tag[1] and tag[9] == tag[10] == tag[4]
    dispatch = next(a for a, t in code.items() if t == 'R0 = PASS R8')
    assert run(dispatch - 3, 3) == ['R8 = DM(0x92003)', 'R2 = DM(0x92004)', 'R3 = DM(0x92005)']    # tag, count, address
    nxt = re.fullmatch(r'JUMP (0x[0-9a-f]+)', code[tag[1] + 5])[1]
    assert run(tag[1], 6) == ['I0 = R3', 'R0 = 0', 'R1 = 0', f'LCNTR = R2, DO {tag[1] + 4:#x} UNTIL LCE',
                              'DM(I0,M6) = R0', f'JUMP {nxt}']
    assert run(tag[4], 7) == ['I0 = R3', f'LCNTR = R2, DO {tag[4] + 5:#x} UNTIL LCE', 'CALL 0x8c033 (DB)', 'NOP', 'NOP',
                              'DM(I0,M6) = R8', f'JUMP {nxt}']
    assert [(a, t) for a, t in code.items() if re.search(r'\bM6 =', t or '')] == [(0x8c00f, 'M6 = 1')]
