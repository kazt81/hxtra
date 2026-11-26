"""tools/patch_freeze.py: the Hold Sustain block (HX_FREEZE): its kernel's place and size in Block 3 and Entry 2, the model,
its knobs and their pids, the browser, the primitive that runs the kernel, Entry 3's size, and whole builds."""
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
        (1, 'Mode', 5, 2), (2, 'Hold', 6, 1), (3, 'Attack', 7, 3), (4, 'Release', 8, 3), (5, 'FXLevel', 9, 3),
        (6, 'DryLevel', 10, 3)]
    src = open(pf.ASM).read()
    for name, pid in (('P_MODE', 5), ('P_HOLD', 6), ('P_ATTACK', 7), ('P_RELEASE', 8), ('P_EFFECT', 9), ('P_DRY', 10)):
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
    assert not hasattr(feature, 'apply') and not hasattr(feature, 'SETTINGS')


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
    assert set(writer) == {5, 6, 7, 8, 9, 10}
    assert all(nodes[writer[p]][3] == (0x0e, p, 1) for p in writer)
    assert b[0x0e:0x10] == [1, 2]                         # writers' path: member 1
    src = {e[1]: e[0] for e in edges}
    assert [src[writer[p]] for p in range(5, 11)] == [slots[k] for k in range(1, 7)]


@pytest.mark.firmware
def test_the_model_and_its_knobs(built):
    _, out, info = built
    m = kit.parse_entry3_full(kit.get_entry_swapped(out, 3))['models'][info['model_id']]
    assert (m['name'], m['displayName'], m['meta']['category']) == (pf.NAME, 'Hold Sustain', 'pitch')
    assert [(q['name'], q['slot'], q['type']) for q in m['params']] == [
        ('Mode', 1, 2), ('Hold', 2, 1), ('Attack', 3, 3), ('Release', 4, 3), ('FXLevel', 5, 3), ('DryLevel', 6, 3)]
    p = {q['name']: q for q in m['params']}
    assert (p['Mode']['meta']['displayType'], p['Mode']['meta']['0'], p['Mode']['meta']['1']) == ('list', 'Momentary', 'Latch')
    assert (p['Hold']['meta']['false'], p['Hold']['meta']['true']) == ('Off', 'On')
    for k, rng in (('Attack', (0.01, 4.0, 0.3)), ('Release', (0.05, 10.0, 1.0))):
        assert (p[k]['meta']['displayType'], p[k]['meta']['units']) == ('time', 'sec')
        assert (p[k]['min'], p[k]['max'], p[k]['default']) == pytest.approx(rng)
    for k, name, short in (('FXLevel', 'FX Level', 'FX Lvl'), ('DryLevel', 'Dry Level', 'Dry Lvl')):
        assert (p[k]['meta']['displayName'], p[k]['meta']['displayNameShort']) == (name, short)
        assert (p[k]['meta']['displayType'], p[k]['meta']['valueMinString']) == ('db', 'Off')
        assert (p[k]['min'], p[k]['max'], p[k]['default']) == (-60.0, 6.0, 0.0)


@pytest.mark.firmware
def test_entry0_shows_six_knobs_and_names_preset_id_380(built):
    data, out, info = built
    m = kit.parse_entry3_full(kit.get_entry_swapped(out, 3))['models'][info['model_id']]
    assert table1(out)[m['words'][2]] == (380, pf.DSP_COST) and 380 not in {pid for pid, _ in table1(data).values()}
    e0 = kit.get_entry_swapped(out, 0)
    segs = kit._parse_e0_segments(e0)
    A = kit.e0_device(segs)
    rd = lambda va, n: e0[kit._e0_vaddr_to_foff(segs, va, n):kit._e0_vaddr_to_foff(segs, va, n) + n]
    u32 = lambda va: struct.unpack('<I', rd(va, 4))[0]
    t2, (_, n2) = u32(A.TAB2_BASE_PTR), kit._decode_thumb_movw(rd(A.TAB2_CNT_INSN, 4))
    assert struct.unpack('<5I', rd(t2 + 44 * (n2 - 1) + 24, 20)) == (6, 6, 6, 0, 0)


@pytest.mark.firmware
def test_the_browser_lists_it_in_a_hold_sustain_folder_under_pitch_synth(built):
    data, out, info = built
    before, after = browser(data), browser(out)
    name_idx = kit.parse_entry3_full(kit.get_entry_swapped(out, 3))['models'][info['model_id']]['words'][2]
    assert after[8] == before[8] + [('Hold Sustain', [(1, name_idx, 'Hold Sustain')])]     # a plain effect: no trails
    assert len(after[8]) == 4
    assert {c: f for c, f in after.items() if c != 8} == {c: f for c, f in before.items() if c != 8}


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
    'HX_FREEZE': '95846d3f6791fc2537587a5ae9a5a97f',                                      # beside 1 NAM slot
    'HX_FREEZE HX_CLICK HX_FX_GATE HX_GR HX_USB_MONITOR HX_GATE_SC HX_REAL_NAMES': 'cb6f2c2a453e7917ae0cf1444eed6992',  # every DSP step, no NAM
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
    assert len(pa.get_entry_swapped(data, 3)) <= DEFAULT_E3
    on = block3.on({f: '1' for f in flags.split()})
    assert pa.E2_MAX - pa.l6ia.parse(data)[2]['payload_len'] == block3.e2_room(block3.slots(env)) - sum(block3.e2(f) for f in on)
