"""tools/patch_freeze.py: the Hold Sustain block (HX_FREEZE): its kernel's place and size in Block 3 and Entry 2, the model,
its knobs and their pids, Hold following the block's on/off, the browser, loading off, the primitive that runs the
kernel, Entry 3's size, and whole builds."""
import hashlib
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import block3
import freeze as fz
import kit_patch_amp as kit
import m4cache
import patch_amp as pa
import patch_freeze as pf
from features import freeze as feature
from test_click import blob_words, browser, check_counts, pmap
from test_gate import DEFAULT_E3, build_steps, ldr_blocks, stock_l6ia, table1

ROOT = Path(__file__).resolve().parent.parent
QUIET = {'log': lambda *a: None}
ALONE = {'HX_FREEZE': '1'}


# ---- the kernel's place and size

def test_the_kernel_sits_where_block3_places_it_beside_one_nam_slot():
    assert block3.slots(ALONE) == 1
    dm, pm = block3.place('HX_FREEZE', ALONE)
    n_dm, n_pm = pf.dsp_size()
    lo, hi = block3.room(1)
    assert dm + n_dm == block3.nw(pm) and pm % 2 == 0 and lo <= dm and block3.nw(pm + n_pm + (n_pm & 1)) == hi
    secs, _ = pa.sasm.assemble(pf.dsp_asm(dm, pm), 'freeze.asm')
    assert pa.ldr_size(secs, records=1) == pf.e2_size() == block3.e2('HX_FREEZE')


def test_its_zero_data_goes_in_as_one_zero_fill_block():
    secs, syms = pf.assembled()
    dm = [s for s in secs if s.kind == 'dm']
    assert [(pa.pack_init_l32(s.addr, s.words)[0], len(s.words)) for s in dm] == [(4, 50), (1, 4017)]


def test_the_instance_fits_the_mono_fx_host():
    _, syms = pf.assembled()
    inst = pf.instance()
    assert inst == {'dm_words': syms['DM_WORDS'], 'pm_words': 0x0d, 'sdram_words': 0x1400}
    assert inst['dm_words'] <= kit.FX_BUDGET[1]['dm'] and inst['sdram_words'] <= kit.FX_BUDGET[1]['sdram']
    assert syms['SDR_NEED'] <= inst['sdram_words']


def test_the_level_knobs_bottom_is_the_kernels_and_the_references_off():
    _, syms = pf.assembled()
    level = {p[1]: p for p in pf.PARAMS}
    assert level['FXLevel'][4] == level['DryLevel'][4] == fz.OFF_DB
    assert fz.Freeze._gain(fz.OFF_DB) == 0.0 and fz.Freeze._gain(fz.OFF_DB + 0.5) > 0.0


def test_the_knobs_are_the_kernels_pids_in_order():
    params = pf.freeze_params()
    assert [(p['slot'], p['name'], p['pid'], p['type']) for p in params] == [
        (1, 'Attack', 5, 3), (2, 'Release', 6, 3), (3, 'FXLevel', 7, 3), (4, 'DryLevel', 8, 3), (5, 'Hold', 9, 1)]
    src = open(pf.ASM).read()
    for name, pid in (('P_ATTACK', 5), ('P_RELEASE', 6), ('P_EFFECT', 7), ('P_DRY', 8), ('P_HOLD', 9)):
        assert f'.equ {name},' in src and pf.assembled()[1][name] == pid


# ---- where the build and the page run it

def test_build_runs_it_after_the_metronome_and_before_the_knob_tools(tmp_path, monkeypatch):
    ran = build_steps(tmp_path, monkeypatch, 'HX_Stomp', {'HX_CLICK': '1', 'HX_FREEZE': '1', 'HX_FX_GATE': '1', 'HX_GR': '1'})
    assert ran.index('tools/patch_click.py') < ran.index('tools/patch_freeze.py') < ran.index('tools/patch_gate.py') \
        < ran.index('tools/patch_comp.py')


def test_web_worker_runs_it_after_the_metronome_and_before_the_knob_tools():
    js = (ROOT / 'web/firmware-worker.js').read_text()
    at = lambda s: js.index(s, js.index('step(5,'))
    assert at('"tools/patch_click.py", "build/') < at('"tools/patch_freeze.py", "build/') < at('"tools/patch_gate.py", "build/')
    for f in ('tools/patch_freeze.py', 'tools/features/freeze.py', 'src/sharc/freeze.asm'):
        assert f'"{f}"' in js


def test_off_unless_asked_for_and_last_on_the_page():
    assert feature.FLAG not in m4cache.web_flags() + m4cache.web_options() and m4cache.web_dsp()[-1] == feature.FLAG
    assert callable(feature.apply) and not hasattr(feature, 'SETTINGS')       # its hooks only (src/m4/freeze.s)


# ---- the firmware it builds (from the stock file: it needs nothing else)

@pytest.fixture(scope='module')
def built():
    data = stock_l6ia()
    out, info = pf.add_freeze(data, **QUIET)
    return data, out, info


@pytest.mark.firmware
def test_each_knob_reaches_its_pid(built):
    _, out, info = built
    b = blob_words(out, info['blob'])
    pm, nodes, edges, slots = pmap(b)
    check_counts(pm, nodes, edges)
    writer = {nodes[k][3][1]: k for k in nodes if nodes[k][0] == 1}
    assert set(writer) == {5, 6, 7, 8, 9}
    assert all(nodes[writer[p]][3] == (0x0e, p, 1) for p in writer)
    assert b[0x0e:0x10] == [1, 2]                         # writers' path: member 1
    src = {e[1]: e[0] for e in edges}
    assert [src[writer[p]] for p in range(5, 10)] == [slots[k] for k in range(1, 6)]


@pytest.mark.firmware
def test_the_model_and_its_knobs(built):
    _, out, info = built
    m = kit.parse_entry3_full(kit.get_entry_swapped(out, 3))['models'][info['model_id']]
    assert (m['name'], m['displayName'], m['meta']['category']) == (pf.NAME, 'Hold Sustain', 'pitch')
    assert [(q['name'], q['slot'], q['type']) for q in m['params']] == [
        ('Attack', 1, 3), ('Release', 2, 3), ('FXLevel', 3, 3), ('DryLevel', 4, 3), ('Hold', 5, 1)]
    p = {q['name']: q for q in m['params']}
    assert (p['Hold']['meta']['false'], p['Hold']['meta']['true']) == ('Off', 'On')
    for k, rng in (('Attack', (0.01, 4.0, 0.1)), ('Release', (0.05, 10.0, 0.5))):
        assert (p[k]['meta']['displayType'], p[k]['meta']['units']) == ('time', 'sec')
        assert (p[k]['min'], p[k]['max'], p[k]['default']) == pytest.approx(rng)
    for k, name, short, dflt in (('FXLevel', 'FX Level', 'FX Lvl', -12.0), ('DryLevel', 'Dry Level', 'Dry Lvl', 0.0)):
        assert (p[k]['meta']['displayName'], p[k]['meta']['displayNameShort']) == (name, short)
        assert (p[k]['meta']['displayType'], p[k]['meta']['valueMinString']) == ('db', 'Off')
        assert (p[k]['min'], p[k]['max'], p[k]['default']) == (-60.0, 6.0, dflt)


@pytest.mark.firmware
def test_hold_follows_the_blocks_on_off_as_the_stock_feedbackers_enable(built):
    # (the M4 matches meta by string index: 'followEnable' 568 and 'true' 209, each once in the stock Entry 3)
    data, out, info = built
    e3 = kit.parse_entry3_full(kit.get_entry_swapped(out, 3))
    p = {q['name']: q for q in e3['models'][info['model_id']]['params']}
    assert p['Hold']['meta']['followEnable'] == 'true'
    assert not [q for q in p if q != 'Hold' and 'followEnable' in p[q]['meta']]
    s = e3['strings']
    assert (s.index('followEnable'), s.index('true'), s.count('followEnable'), s.count('true')) == (568, 209, 1, 1)
    stock = kit.parse_entry3_full(kit.get_entry_swapped(data, 3))
    assert kit.find_model(stock, 'VIC_FeedbackSim')['params'][-1]['meta']['followEnable'] == 'true'


@pytest.mark.firmware
def test_entry0_shows_four_knobs_follows_the_on_off_and_names_preset_id_380(built):
    data, out, info = built
    m = kit.parse_entry3_full(kit.get_entry_swapped(out, 3))['models'][info['model_id']]
    assert table1(out)[m['words'][2]] == (380, pf.DSP_COST) and 380 not in {pid for pid, _ in table1(data).values()}
    e0 = kit.get_entry_swapped(out, 0)
    segs = kit._parse_e0_segments(e0)
    A = kit.e0_device(segs)
    rd = lambda va, n: e0[kit._e0_vaddr_to_foff(segs, va, n):kit._e0_vaddr_to_foff(segs, va, n) + n]
    u32 = lambda va: struct.unpack('<I', rd(va, 4))[0]
    t2, (_, n2) = u32(A.TAB2_BASE_PTR), kit._decode_thumb_movw(rd(A.TAB2_CNT_INSN, 4))
    assert struct.unpack('<5I', rd(t2 + 44 * (n2 - 1) + 24, 20)) == (4, 5, 5, 1, 0)


@pytest.mark.firmware
def test_the_browser_lists_it_last_in_pitch_synth_mono_as_block_kind_24(built):
    # (kind 24, Poly Pitch's: the block's off sends bypassMode 0, so the kernel plays the input and the release)
    data, out, info = built
    before, after = browser(data), browser(out)
    name_idx = kit.parse_entry3_full(kit.get_entry_swapped(out, 3))['models'][info['model_id']]['words'][2]
    (mono, items), *rest = before[8]
    assert mono == 'Mono' and (24, 0x621, 'Poly Pitch') in items
    assert after[8] == [(mono, items + [(24, name_idx, 'Hold Sustain')]), *rest]
    assert {c: f for c, f in after.items() if c != 8} == {c: f for c, f in before.items() if c != 8}


def movws(e0, va, n):
    """The immediates of the n `movw r2, #imm; cmp r3, r2; beq ...` from va on (beq or beq.w)."""
    segs = kit._parse_e0_segments(e0)
    at, out = kit._e0_vaddr_to_foff(segs, va, 4), []
    for _ in range(n):
        out.append(kit._decode_thumb_movw(e0[at:at + 4])[1])
        at += 8 if e0[at + 7] == 0xd0 else 10
    return out


@pytest.mark.firmware
def test_it_loads_off_in_place_of_infinite_sustain_which_no_browser_list_has(built):
    data, out, info = built
    name_idx = kit.parse_entry3_full(kit.get_entry_swapped(out, 3))['models'][info['model_id']]['words'][2]
    assert info['load_off'] == [0x28dfc668, 0x28dfd20a]
    e0, e0_stock = kit.get_entry_swapped(out, 0), kit.get_entry_swapped(data, 0)
    for va in info['load_off']:
        assert movws(e0_stock, va, 7) == [pf.LOAD_OFF, 0x6f1, 0x777, 0xc07, 0x78a, 0xc0b, 0x8a8]
        assert movws(e0, va, 7) == [name_idx, 0x6f1, 0x777, 0xc07, 0x78a, 0xc0b, 0x8a8]
    stock = kit.parse_entry3_full(kit.get_entry_swapped(data, 3))
    assert stock['strings'][pf.LOAD_OFF] == 'L6SPB_InfSustain'
    assert not [i for c in browser(data).values() for _, items in c for i in items if i[1] == pf.LOAD_OFF]
    with pytest.raises(SystemExit, match='found 0 load-off lists'):
        pf.load_off(e0, name_idx)


@pytest.mark.firmware
def test_the_primitive_runs_the_kernel_and_its_zeros_are_one_zero_fill_block(built):
    _, out, info = built
    dm, pm = info['place']
    blocks = ldr_blocks(out)
    assert (4, pf.PRIM[1], (pf.PRIM[0], *pf.REGISTRY, info['entry'], 0x91, 0x0d)) in blocks
    secs, syms = pa.sasm.assemble(pf.dsp_asm(dm, pm), 'freeze.asm')
    assert info['entry'] == syms['CUSTOM_AMP_ENTRY'] == pm
    code = next(b for t, a, b in blocks if t == 5 and a == pm)
    words = [s for s in secs if s.kind == 'pm'][0].words
    raw = b''.join(int(x).to_bytes(6, 'little') for x in list(words) + [0] * (len(words) & 1))
    assert code == struct.unpack('<%dI' % (len(raw) // 4), raw)
    assert (1, dm + 50, ()) in blocks                     # 4,017 zero words: three LDR words
    init = next(s for s in secs if s.kind == 'dm' and s.addr == dm)
    assert next(b for t, a, b in blocks if t == 4 and a == dm) == tuple(init.words)


@pytest.mark.firmware
def test_entry3_goes_back_home_after_the_model(built):
    # (an add-model's Entry 3 grows past where amps still load: patch_comp.e3_add_strings puts the section back)
    _, out, _ = built
    assert len(kit.get_entry_swapped(out, 3)) <= DEFAULT_E3


@pytest.mark.firmware
def test_a_second_run_is_refused(built):
    _, out, _ = built
    with pytest.raises(SystemExit, match='already in this image'):
        pf.add_freeze(out, **QUIET)


FREEZE_BUILT_MD5 = {
    'HX_FREEZE': '150ea6d7a0f8ef1b10c2b9daca99f839',                                      # beside 1 NAM slot
    'HX_FREEZE HX_CLICK HX_FX_GATE HX_GR HX_USB_MONITOR HX_GATE_SC HX_REAL_NAMES': 'dcb038f363c0236195318b6db96b451f',  # every DSP step, no NAM
}


@pytest.mark.firmware
@pytest.mark.parametrize('flags', FREEZE_BUILT_MD5)
def test_freeze_build(tmp_path, flags):
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    out = tmp_path / 'freeze.hxf'
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_') or k == 'HX_STOMP_HXF'} | {f: '1' for f in flags.split()}
    r = subprocess.run([sys.executable, str(ROOT / 'build.py'), stock, '-o', str(out), '--no-check'],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'ALL OK' in r.stdout and '[+] Entry 0: preset_id 380' in r.stdout
    assert hashlib.md5(out.read_bytes()).hexdigest() == FREEZE_BUILT_MD5[flags]
    data = pa.load_l6ia_from_any(str(out))[0]
    name_idx = kit.find_model(kit.parse_entry3_full(pa.get_entry_swapped(data, 3)), pf.NAME)['words'][2]
    for va in (0x28dfc668, 0x28dfd20a):                   # (the later steps keep its name's index)
        assert movws(kit.get_entry_swapped(data, 0), va, 1) == [name_idx]
    assert len(pa.get_entry_swapped(data, 3)) <= DEFAULT_E3
    on = block3.on({f: '1' for f in flags.split()})
    assert pa.E2_MAX - pa.l6ia.parse(data)[2]['payload_len'] == block3.e2_room(block3.slots(env)) - sum(block3.e2(f) for f in on)
