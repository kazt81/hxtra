"""tools/features/freeze.py and src/m4/freeze.s: Hold Sustain loads off. The two handlers in unicorn (a block record of it saved on
reads off, any other record as saved; a lit footswitch node of an off Hold Sustain goes unlit in the stock unlit colour, any other
node as saved), each before the stock call through patch_menu's chain; the stock code they follow, and the firmware it builds, each
handler before its own call."""
import struct

import pytest

import features
import patch_freeze as pf
import patch_menu as pm
import setting_ids
from features import freeze as fz
from firmware import branch_target, built, reader, stock_e0

MODS = features.load()
IDS = setting_ids.by_name()
MOD, CHAIN = 0x28e60000, 0x28e61000
REC, NODE, LIST, RGBS = 0x28700000, 0x28700400, 0x28700800, 0x28700c00
GRAPH, MEMSET, BLOCK_INFO, BYPASSED, COLOUR, RGB = 0x28d92a98, 0x28e24b78, 0x28e0fe94, 0x28e04514, 0x28e0f0ec, 0x28db7e1c
GRAPH_OBJ, HANDLE, LED_COLOUR = 0x28a00000, 7, 8
LIT, UNLIT = b'\x06\xff\x00', b'\x01\x09\x00'
_code = []


class Freeze:
    """freeze.s in tests/m4emu.py's M4. self.blocks: block handle -> (preset model ID, on); a handle not in it is unknown, as stock
    BLOCK_INFO and BYPASSED leave their output unwritten for one (info_fails: BLOCK_INFO returns -1 instead)."""

    def __init__(self, m4emu):
        if not _code:
            _code.append(m4emu.assemble(fz.MODULE, MODS, IDS, inc={'freeze.inc': f'.equ FREEZE_ID, {fz.PRESET_ID}\n'}))
        code, self.sym = _code[0]
        self.m = m = m4emu.M4(code, MOD)
        self.blocks, self.info_fails, self.bypassed_fails = {HANDLE: (fz.PRESET_ID, False)}, False, False
        self.slot_known = True          # False: BYPASSED finds no slot for the block, writes nothing and returns 0, as stock
        m.stub(GRAPH, lambda m: m.reg('r0', GRAPH_OBJ))
        m.stub(MEMSET, lambda m: m.write(m.reg('r0'), bytes([m.reg('r1') & 0xff]) * m.reg('r2')))
        m.stub(BLOCK_INFO, self._info)
        m.stub(BYPASSED, self._bypassed)
        m.stub(COLOUR, lambda m: (m.u8(m.reg('r3'), LED_COLOUR), m.reg('r0', 0)))
        m.stub(RGB, lambda m: m.reg('r0', RGBS + 4 * m.reg('r1')))
        m.write(RGBS, UNLIT + b'\0' + LIT + b'\0')

    def _info(self, m):
        block, info = m.reg('r1'), m.reg('r2')
        if block in self.blocks:
            m.write(info + 1, struct.pack('<I', self.blocks[block][0]))
        m.reg('r0', -1 if self.info_fails else 0)

    def _bypassed(self, m):
        if m.reg('r1') in self.blocks and self.slot_known:
            m.u8(m.reg('r2'), int(not self.blocks[m.reg('r1')][1]))
        m.reg('r0', -1 if self.bypassed_fails else 0)

    def call(self, sym, *args):
        self.m.log.clear()
        return self.m.call(MOD + self.sym[sym], *args)

    def record(self, typ, pid, on):
        rec = bytearray(0x122)
        rec[0], rec[0xf] = typ, on
        struct.pack_into('<I', rec, 6, pid)
        self.m.write(REC, rec)
        return bytes(rec)

    def node(self, typ=1, lit=1, block=HANDLE):
        node = bytearray(0x38)
        node[9], node[0x20], node[0x21:0x24] = typ, lit, LIT if lit else UNLIT
        struct.pack_into('<I', node, 0xc, block)
        self.m.write(NODE, node)
        return bytes(node)


@pytest.fixture
def frz(m4emu):
    return Freeze(m4emu)


def test_the_preset_id_is_the_models():
    assert pf.PRESET_ID == fz.PRESET_ID == 380


def test_a_hold_sustain_record_saved_on_reads_off(frz):
    rec = frz.record(6, fz.PRESET_ID, 1)
    frz.call('freeze_rec_off', 0x28a00000, 0x28c00000, REC)
    assert frz.m.read(REC, len(rec)) == rec[:0xf] + b'\0' + rec[0x10:]


@pytest.mark.parametrize('typ, pid, on', [(6, fz.PRESET_ID, 0), (6, fz.PRESET_ID + 1, 1), (6, 0x1a5, 1), (7, fz.PRESET_ID, 1),
                                          (8, fz.PRESET_ID, 1), (6, 0x10000 + fz.PRESET_ID, 1)])    # (the ID is a whole u32)
def test_any_other_record_reads_as_saved(frz, typ, pid, on):
    rec = frz.record(typ, pid, on)
    frz.call('freeze_rec_off', 0x28a00000, 0x28c00000, REC)
    assert frz.m.read(REC, len(rec)) == rec


def test_a_lit_footswitch_of_an_off_hold_sustain_goes_unlit_as_a_press_leaves_it(frz):
    node = frz.node()
    frz.call('freeze_fs_unlit', LIST, NODE)
    assert frz.m.read(NODE, len(node)) == node[:0x20] + b'\0' + UNLIT + node[0x24:]
    assert [r[:2] for r in frz.m.calls(BLOCK_INFO)] == [r[:2] for r in frz.m.calls(BYPASSED)] == [(GRAPH_OBJ, HANDLE)]
    assert [r[:3] for r in frz.m.calls(COLOUR)] == [(GRAPH_OBJ, HANDLE, 1)]
    assert [r[:2] for r in frz.m.calls(RGB)] == [(LED_COLOUR, 0)]


@pytest.mark.parametrize('blocks, info_fails, bypassed_fails, slot_known', [
    ({HANDLE: (fz.PRESET_ID, True)}, False, False, True),           # the block is on
    ({HANDLE: (fz.PRESET_ID + 1, False)}, False, False, True),      # another model
    ({}, False, False, True),                                       # an unknown block: the lookups write nothing and return 0
    ({HANDLE: (fz.PRESET_ID, False)}, True, False, True),           # BLOCK_INFO fails
    ({HANDLE: (fz.PRESET_ID, False)}, False, True, True),           # BYPASSED fails
    ({HANDLE: (fz.PRESET_ID, False)}, False, False, False)])        # BYPASSED finds no slot
def test_any_other_lit_block_footswitch_stays_as_saved(frz, m4emu, blocks, info_fails, bypassed_fails, slot_known):
    frz.blocks, frz.info_fails, frz.bypassed_fails, frz.slot_known = blocks, info_fails, bypassed_fails, slot_known
    frame = bytearray(0x38)                                 # the handler's frame as a stale one that would unlight it
    struct.pack_into('<I', frame, 1, fz.PRESET_ID)
    frame[0x34] = 1
    frz.m.write(m4emu.STACK_TOP - 0x40, frame)
    node = frz.node()
    frz.call('freeze_fs_unlit', LIST, NODE)
    assert frz.m.read(NODE, len(node)) == node and not frz.m.calls(RGB)


@pytest.mark.parametrize('typ, lit', [(2, 1), (1, 0)])
def test_a_command_node_or_an_unlit_one_is_left_without_a_call(frz, typ, lit):
    node = frz.node(typ, lit)
    frz.call('freeze_fs_unlit', LIST, NODE)
    assert frz.m.read(NODE, len(node)) == node and not frz.m.log


@pytest.mark.parametrize('sym, original, args', [('freeze_rec_off', fz.APPLY_RECORD, (0x28a00000, 0x28c00000, REC)),
                                                 ('freeze_fs_unlit', fz.LIST_ADD, (LIST, NODE))])
def test_each_runs_before_the_stock_call_which_gets_its_arguments(frz, sym, original, args):
    frz.record(6, fz.PRESET_ID, 1)
    frz.node()
    seen = []
    frz.m.stub(original, lambda m: (seen.append((m.reg('r0'), m.reg('r1'), m.reg('r2'), m.read(REC + 0xf, 1)[0],
                                                 m.read(NODE + 0x20, 1)[0])), m.reg('r0', 0x77)))
    frz.m.load(CHAIN, pm.chain_cave(CHAIN, original, [MOD + frz.sym[sym]], []))
    assert frz.m.call(CHAIN, *args) == 0x77
    (r0, r1, r2, on, lit), = seen
    assert (r0, r1) == args[:2] and (len(args) < 3 or r2 == args[2])
    assert (on, lit) == ((0, 1) if sym == 'freeze_rec_off' else (1, 0))


def imm16(hw):
    """(opcode, rd, imm16) of a Thumb-2 movw or movt."""
    h1, h2 = struct.unpack('<2H', hw)
    return h1 & 0xfbf0, h2 >> 8 & 0xf, (h1 & 0xf) << 12 | (h1 >> 10 & 1) << 11 | (h2 >> 12 & 7) << 8 | h2 & 0xff


@pytest.mark.firmware
def test_the_handlers_follow_the_stock_code():
    """A preset load's record apply keeps the record in r6: its model's preset ID a u32 at +6, its on at +0xf (read once, for
    the final on/off). The stock footswitch toggle clears a 0x34-byte info, looks the node's block (+0xc) up, takes its colour
    and lit (+0x20) and stores the RGB at +0x21..0x23, through the functions freeze.s calls; its type is at +9."""
    read = reader(stock_e0())
    assert read(0x28e0cc92, 2) == bytes.fromhex('1646'), 'mov r6, r2'
    assert read(0x28e0ced4, 4) == bytes.fromhex('d6f80630'), 'ldr.w r3, [r6, #6]'
    assert read(0x28e0d364, 2) == bytes.fromhex('f27b'), 'ldrb r2, [r6, #0xf]'
    assert read(0x28dd113e, 2) == bytes.fromhex('637a'), 'ldrb r3, [r4, #9]'
    assert read(0x28dd1190, 4) == bytes.fromhex('0021 3422'), 'movs r1, #0; movs r2, #0x34'
    for at, fn in ((0x28dd1196, MEMSET), (0x28dd119a, GRAPH), (0x28dd11a2, BLOCK_INFO), (0x28dd11bc, GRAPH), (0x28dd11c8, COLOUR),
                   (0x28dd11de, RGB)):
        assert branch_target(at, read(at, 4)) == fn
    assert read(0x28dd119e, 2) == bytes.fromhex('e168'), 'ldr r1, [r4, #0xc]'
    assert read(0x28dd11cc, 4) == bytes.fromhex('94f82010'), 'ldrb.w r1, [r4, #0x20]'
    assert read(0x28dd11e2, 12) == bytes.fromhex('0388 8278 84f82320 a4f82130'), 'the RGB into +0x21..0x23'


@pytest.mark.firmware
def test_the_build_runs_each_handler_before_its_own_stock_call(m4emu, monkeypatch):
    seen, real = {}, pm.Patch.module

    def module(self, path, inc=None):
        seen[path] = inc
        return real(self, path, inc)

    monkeypatch.setattr(pm.Patch, 'module', module)
    stock = reader(stock_e0())
    read, on = built({'HX_FREEZE': '1'})
    assert 'freeze' in on and seen[fz.MODULE] == {'freeze.inc': f'.equ FREEZE_ID, {fz.PRESET_ID}\n'}
    code, sym = m4emu.assemble(fz.MODULE, MODS, IDS, inc=seen[fz.MODULE])
    for site, original, handler in ((fz.APPLY_SITE, fz.APPLY_RECORD, 'freeze_rec_off'),
                                    (fz.FS_ADD_SITE, fz.LIST_ADD, 'freeze_fs_unlit')):
        assert stock(site, 4) == pm.bl(site, original)
        stub = branch_target(site, read(site, 4))
        module_at = branch_target(stub + 6, read(stub + 6, 4)) - sym[handler]       # push, ldm, then the before handler
        assert read(module_at, len(code)) == code
        lo, hi = imm16(read(stub + 14, 4)), imm16(read(stub + 18, 4))             # ldm, then the original into r12
        assert (lo[:2], hi[:2]) == ((0xf240, 12), (0xf2c0, 12)) and hi[2] << 16 | lo[2] == original | 1
