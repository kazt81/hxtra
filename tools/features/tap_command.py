"""Tap command: a Tap command for FS1..FS5 in the Command Center, so tap tempo lives in the presets that want it (issue #108). A
Stomp footswitch whose slot holds it taps the tempo as the TAP footswitch does, and its ring blinks the tempo as the TAP ring does,
in Tap LED Color's colour when that is built (src/m4/tap_command.s). The preset keeps it as type 9, the Helix's CV Out, complete in
every Command Center table but never offered on the HX Stomp; stock firmware gives it no footswitch node, so there it does nothing.
A footswitch with no block reads Tap on the Home screen, as one with another command reads that command's name. The Command
Center's code: docs/research/m4/command-center.md."""
from features import tap_color

FLAG = 'HX_CC_TAP'
MENU = False
ORDER = 120                         # after tap_color, whose ring colour handlers it calls
MODULE = 'src/m4/tap_command.s'

TAP = 9
CC = 0x281252b8
CC_GET = 0x28d96094                 # () -> the Command Center
FS_SLOTS = range(6, 11)
# The FS slots' Command knob: how many places (words, one a slot, read only by 0x28de57bc), and type 9's name and knob count
CHOICES, FS_CHOICES = 0x28e3c5f4, 10
NAMES, NAME = 0x28e3c628, b'Tap'
COUNTS, CV_OUT_COUNT = 0x28e3c6d8, 2                    # the Command knob and CV Value: Tap has the Command knob alone
FIRE, FIRE_CALL = 0x28de5cd4, 0x28dd1342                # the stomp toggle's fire of every command but Looper and Snapshot's
NODE_NAME, NODE_CALLS = 0x28dd568c, (0x28dd88d2, 0x28dd8a68)    # the footswitch node insert naming a command's node: 0 for type 9
CHOICE, CHOICE_CALLS = 0x28de57d0, (0x28dbd366, 0x28dbd4d0, 0x28dbd9fa)     # type -> place: the knob, paste checks
STEP, STEP_CALL = 0x28de64a0, 0x28dbd6bc                # the Command knob's turn
FS_STATE = 0x28d9607c
BEAT_RUN_CALLS = (0x28d9be3a, 0x28d9be4c)               # the stock beat's "is FS3 TAP" before it works out a turn
BEAT_ON_CALL = 0x28d9be92                               # its turn on, before FS3's colour and on
LED_MODE, BEAT_OFF_CALL = 0x28db8260, 0x28d9beba        # its turn off: LED 2 off
REFRESH_CALL = 0x28dd0b70                               # the footswitch LED refresh, before each ring's function
SETTING_CALL = 0x28dd276c                               # a tempo setting's change (external clock too) looking for a TAP footswitch


def tap_inc(p):
    tap = p.modules.get(tap_color.MODULE)
    led, again = (tap['tap_led'] | 1, tap['tap_led_again'] | 1) if tap else (0, 0)
    return f'.equ TAP_LED, {led:#x}\n.equ TAP_LED_AGAIN, {again:#x}\n'


def apply(p):
    if p.u32(CC_GET + 4) != CC:                         # ldr r0, [pc, #0]; bx lr; then the word
        raise SystemExit('patch-menu: the Command Center is not where tap_command.s looks for it')
    m = p.module(MODULE, inc={'tap.inc': tap_inc(p)})
    for s in FS_SLOTS:
        p.expect(CHOICES + 4 * s, FS_CHOICES.to_bytes(4, 'little'), "an FS slot's Command knob places")
        p.put(CHOICES + 4 * s, (FS_CHOICES + 1).to_bytes(4, 'little'), "an FS slot's Command knob places")
    p.expect(NAMES + 8 * TAP, b'CV Out\0\0', "type 9's name")
    p.put(NAMES + 8 * TAP, NAME.ljust(8, b'\0'), "type 9's name")
    p.expect(COUNTS + TAP, bytes([CV_OUT_COUNT]), "type 9's knob count")
    p.put(COUNTS + TAP, b'\x01', "type 9's knob count")
    p.own_call(FIRE_CALL, FIRE, 'the stomp toggle firing its command', m['tc_fire'])
    for site in NODE_CALLS:
        p.own_call(site, NODE_NAME, f'the footswitch node insert naming a command at {site:#x}', m['tc_node'])
    for site in CHOICE_CALLS:
        p.own_call(site, CHOICE, f'the Command knob place at {site:#x}', m['tc_choice'])
    p.own_call(STEP_CALL, STEP, 'the Command knob turn', m['tc_step'])
    for site in BEAT_RUN_CALLS:
        p.own_call(site, FS_STATE, f'the stock beat asking for a TAP footswitch at {site:#x}', m['tc_running'])
    p.own_call(BEAT_ON_CALL, FS_STATE, "the stock beat's turn on", m['tc_on'])
    p.own_call(BEAT_OFF_CALL, LED_MODE, "the stock beat's turn off", m['tc_off'])
    p.own_call(REFRESH_CALL, FS_STATE, 'the footswitch LED refresh', m['tc_refresh'])
    p.own_call(SETTING_CALL, FS_STATE, "a tempo setting's change", m['tc_setting'])
